# ADR-021: Application Targeting and Focus

## Status

Accepted (implemented)

## Date

2026-08-06

## Author

Development Team

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-08-06 | 1.0 | Optional `focus_target()` on the capture **and** actuator ports; `Focus` RPC on both services; `capture.window_title` / `capture.focus_before_capture` / `actuator.window_title` config; `Bring App To Front` keyword. |
| 2026-08-07 | 1.1 | **Window-scoped capture**: `capture_window()` / `frame_geometry()` on the capture port, `CaptureFrame` (pixels + origin + device space), `window_title` on `GrabRequest` and geometry on `GrabResponse`, `capture.window_scope` config, Viewer strategy path honours the connected target. Coordinate space defined as the **virtual desktop**; `device_origin()` on the actuator port; DPI-awareness ordering fixed. |

## Context

VizDOM captures the **whole screen** and actuates by **absolute coordinate**. Both
of those are silently wrong whenever the application under test (SUT) is not the
foreground window:

- `capture()` photographs whatever is on top. If a chat window, an IDE, or the test
  runner's own console covers the SUT, the pipeline builds a Visual DOM of the
  *wrong application* — and every subsequent locator dutifully fails (or worse,
  matches a same-named control in the wrong app).
- `tap(nx, ny)` clicks whatever window occupies that point, and `type_text()` goes
  to whatever holds **keyboard focus**. A test can therefore type its input into
  another application entirely. Nothing in the DOM can detect this: the coordinates
  were correct for the screenshot, and the screenshot was correct for its moment.

The project had already met this problem twice and worked around it locally:

1. The **Viewer** hides its own window before grabbing, and its Windows plugin
   carries a hardened `bring_to_front()` (Z-order restore plus three escalating
   techniques) — proven code, but reachable only from the GUI tool.
2. `WindowsCapture.describe_target()` (ADR-018) already walks the Z-order *past our
   own process* to name the app actually under test — an admission that "the
   foreground window" and "the SUT" routinely differ.

So the capability existed but sat in the wrong layer: a Robot Framework suite, a
CLI run, or a remote service could not reach it. Meanwhile ADR-018/019 had made
capture and actuation *remote-capable*, which adds a twist — focus can only be
performed on the machine that owns the screen, so it cannot be a client-side
concern at all in a distributed run.

Raising a window is also not free of consequences, which is why it cannot simply be
done on every grab:

- it **mutates SUT state** — raising a window can dismiss tooltips, transient
  popups, or menus, and it moves keyboard focus;
- it **can be refused**. Windows' foreground lock blocks `SetForegroundWindow` from
  background processes; no technique is guaranteed;
- it is **asynchronous** — the window is not foreground the instant the call
  returns;
- the **target may be ambiguous** ("Notepad" matching two windows) or absent.

## Decision

### 1. An optional capability on both driven ports

Add `focus_target(title=None) -> bool` to `CaptureStrategy` **and**
`ActuatorStrategy`, defaulting to `return False` — exactly the pattern
`describe_target()` established. Each strategy names its own target, because only
it knows how:

| Strategy | Mechanism |
|---|---|
| `windows` capture / `desktop` actuator (Win32) | `ShowWindow(SW_RESTORE)` → `AttachThreadInput` → synthetic Alt tap → temporary `HWND_TOPMOST` → verify |
| `linux` capture / `desktop` actuator (X11) | `wmctrl -a`, then `xdotool windowactivate --sync` → verify |
| `android` (capture + actuator) | `am start -n pkg/.Activity` (or `monkey` launcher intent for a bare package) → verify against the resumed activity |
| `camera` | `False` — a camera observes an external display it cannot control |
| `grpc` (capture + actuator) | forwards a `Focus` RPC to the service (below) |

The Win32 and X11 mechanics live in `adapters/outbound/win32_window.py` and
`x11_window.py`, shared by the capture and actuator strategies rather than
duplicated.

### 2. Verify, never assume

`focus_target()` returns `True` **only** when the strategy confirmed the target is
foreground (Win32: `GetForegroundWindow()` after a settle delay; X11: the active
window title; Android: the resumed activity). The promoted Viewer code returned
`True` whenever it had not thrown, which cannot distinguish "raised" from "the OS
refused" — precisely the case that produces a wrong screenshot. Returning an honest
`False` is what lets the caller fail loudly.

Ambiguity is a failure, not a guess: a title matching several windows logs the
candidates and returns `False`. (An *exactly* duplicated title — an app owning a
hidden twin window — is resolved by Z-order, and says so in the log.)

### 3. Focus crosses the wire as its own RPC

Both protos gain `rpc Focus(FocusRequest) returns (FocusResponse)`. The server runs
its local strategy's `focus_target()` and returns the **verified** boolean plus a
human-readable `detail`. Without this, the feature would be unavailable in exactly
the configuration the reference demo uses (capture *and* actuator over gRPC).

A refusal is a normal response, not a gRPC error — the client decides whether an
unfocusable window should fail the test. Servers accept `--window-title` as the
default target for clients that send none.

### 4. Two ways to use it — explicit keyword and opt-in flag

- **`Bring App To Front  [title]  [required=True]`** — the explicit step. Tries the
  capture port then the actuator port, so a mixed setup (camera capture + desktop
  actuator) still works. **Fails the keyword** when nothing could focus the target;
  `required=${False}` downgrades that to a warning.
- **`capture.focus_before_capture: true`** — raises `capture.window_title` before
  every grab (including the ADR-023 element recap). Here a failure only **warns**:
  the grab may still be usable and one transient foreground lock should not abort a
  suite. The explicit keyword remains the way to make focus fatal.

Config: `capture.window_title`, `capture.focus_before_capture`,
`actuator.window_title` (inherits `capture.window_title` when omitted, since both
ports normally drive the same app). Equivalent library arguments `app_title=` /
`focus_before_capture=` cover use without a config file.

The title is passed **per call** rather than baked into the client strategy's
constructor, so the same code path serves a local grabber and a remote strategy
(whose constructor takes no title — the RPC carries it).

### 5. Capture the window, not the screen — with its geometry

Focusing makes the SUT *visible*; it does not stop the DOM from containing every
other window on the desktop. `capture_window(title)` returns a **`CaptureFrame`** —
the window's client area **plus** `origin`, `device_origin` and `device_size` — and
`window_scope: true` makes it the default for a session (`Capture Screen`,
`Dump Visual DOM`, and the ADR-023 recap all go through one grab helper, because
mixing a cropped and a full-screen grab within a session would invalidate cached
element bounds).

The geometry is not optional decoration. Actuators take **normalized [0,1]**
coordinates over the device's space, so a DOM built from a 402×658 crop and mapped
back against a 1920×1080 screen puts every click in the wrong place. A bare crop is
therefore a trap; the frame carries what is needed to undo it:

```
screen_px  = origin + crop_px
normalized = (screen_px - device_origin) / device_size
```

Three properties of that space were established the hard way (each was a live bug):

1. **It is the virtual desktop, not a monitor.** The capture side first normalized
   against the monitor it grabbed (1920 wide) while the actuator used the whole
   desktop (3840 wide): a click meant for x=−710 on the second display landed at
   x=+499 on the primary. Both ports now derive the space from one helper.
2. **A full-screen grab needs geometry too.** Once the actuator spanned the virtual
   desktop, a plain grab of the primary monitor mapped its centre (0.5) to x=0 — the
   boundary between the two displays. Hence `frame_geometry()`: a strategy states
   where its plain frames sit. Returning None means "no relation to a larger space"
   and the caller normalizes against the image, which is correct for Android, where
   the screencap buffer need not share the input resolution.
3. **The geometry must be read in the right DPI context.** Window rectangles are
   reported in the process's DPI space; screenshots are physical pixels. Worse,
   `import pyautogui` calls `SetProcessDPIAware()`, awareness cannot be changed
   afterwards, and `GetSystemMetrics` then reports a desktop scaled *non-uniformly*
   when monitors differ (here ×1.125 in x, ×1.25 in y) — so it cannot be corrected
   after the fact. Two defences: per-monitor-v2 awareness is claimed **before**
   pyautogui is imported, and the virtual desktop is read from the display driver
   (`EnumDisplaySettings`), which is awareness-independent. A residual mismatch is
   reported with the fix ("import VisualGuiLibrary before pyautogui") rather than
   silently misplacing clicks.

Over gRPC the crop happens **server-side**: `GrabRequest.window_title` asks for it
and `GrabResponse` carries the geometry. Only that machine knows where the window
is, and asking for the rectangle separately would both race a moving window and cost
a second round trip. A strategy that cannot scope to a window answers
`FAILED_PRECONDITION`, and the client falls back to a full-screen grab with a
warning rather than pretending the frame is window-scoped.

In the **Viewer**, selecting a capture strategy previously bypassed the connected
target completely, so "Connect → Calculator" then capturing via the capture service
analysed the whole primary monitor — which on a multi-monitor desktop need not even
contain the app. The strategy path now uses the connected window's title.

## Consequences

**Positive**

- Removes a whole class of silent wrongness: DOMs built from the wrong window, and
  clicks/keystrokes delivered to the wrong application.
- Works distributed. Focus happens where the screen is, which is the only place it
  can happen.
- The Viewer's proven Windows implementation is now reachable from Robot Framework,
  the CLI, and remote services — one implementation instead of two.
- Off by default: no existing suite changes behaviour.

**Negative / limits**

- **Not guaranteed.** The foreground lock can defeat every technique; the honest
  answer is then `False` and the test must decide. Verification makes this visible
  rather than mysterious.
- **Focusing is an action.** It can dismiss transient UI. This is why it is opt-in
  rather than implicit in `capture()`.
- **Wayland and macOS return `False`** (no unprivileged API / not implemented);
  X11 needs `wmctrl` or `xdotool` installed.
- **Title-based targeting is a weak identifier** — a title can change with document
  state. Ambiguity fails loudly instead of guessing, but a stable window title is
  still the caller's responsibility.
- The `Focus` RPC extends both service contracts; older servers reject it (the
  client logs the failure and returns `False`).
- **A cropped capture reads the desktop, so the window must be unoccluded.** That is
  why `capture_window()` requires *verified* focus and returns None otherwise.
  Capturing an occluded window directly (Win32 `PrintWindow`) would remove the
  requirement but returns black frames for GPU-composited content — noted as future
  work, not a replacement.
- **A window straddling two monitors is captured on its dominant one and clipped.**
  Stitching across displays would make every element's coordinates depend on the
  desktop layout; the clipping is logged.
- **Window scope changes what the DOM contains**, so element bounds from a
  window-scoped session are not comparable with a full-screen one. The session
  records `capture_scope` for exactly this reason.
- **DPI awareness is process-global and first-come-first-served.** If a foreign
  import claims it first, clicks on a scaled multi-monitor desktop may be misplaced
  and VizDOM can only report it.
- Monitor re-arrangement mid-run is not supported (the virtual rect is cached).

## Alternatives Considered

1. **Keep it in the Viewer only** — rejected: the correctness problem belongs to
   every client, not just the GUI tool.
2. **Focus implicitly inside every `capture()`** — rejected: it hides a
   state-mutating action inside a read, and would fire on every recap.
3. **Capture only the SUT window's rectangle instead of the full screen**
   (`PrintWindow`) — attractive because it needs no focus at all, but it does not
   help actuation (clicks still need the window to be on top), is Windows-specific,
   and breaks for GPU-composited/occluded content. Worth revisiting as a *capture*
   option; it does not replace focus.
4. **A dedicated "window manager" port** — rejected as premature: two strategies
   already own the platform knowledge, and a third port would need its own
   registry, config section, and service for no new capability.
5. **Return `True` optimistically (the original Viewer behaviour)** — rejected; see
   §2.

## References

- ADR-018 Pluggable Capture Service (`describe_target`, the same optional-hook
  pattern)
- ADR-019 Pluggable Actuator Service (normalized coordinate contract)
- ADR-020 Client Session Config (`capture` / `actuator` sections)
- ADR-023 Post-Action Recap (the recap re-grab also honours the focus flag)
- `tools/visual_dom_viewer/plugins/windows_handler.py` — the origin of the Win32
  escalation sequence
