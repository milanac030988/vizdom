# ADR-025: Session Orchestrator Service (deferred)

## Status

**Proposed — deliberately not implemented.** This ADR records the option, the
comparison, and the conditions that would make it necessary, so the decision is
traceable rather than implicit.

## Date

2026-08-09

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-08-09 | 1.0 | Records the orchestration question: rejects a forwarding gateway outright; accepts a *session orchestrator* as the correct future shape and defers it against named trigger conditions. |

## Context

Today the **client orchestrates**. A Robot Framework suite (or a Python caller)
holds the session and drives the flow itself:

```
client:  capture()  ->  detect()  ->  OCR / merge / reading order / hierarchy / compile
         -> DOM cached in the client -> resolve locator -> normalise -> actuate()
```

Only the three *driven ports* are optionally remote (ADR-017/018/019). Each of
them earns its remoteness from **physical locality**: capture must run where the
screen is, actuation where the input hardware is, detection where the GPU is.
All three are **stateless** — a warm model is a cache, not session state.

Two observations prompted the question of whether an orchestration tier belongs
in this picture:

1. **A client must know three addresses.** The config carries `detector.grpc_target`,
   `capture.target`, `actuator.target`. It works, but it is three coordinates for
   what a user experiences as one system.
2. **The pipeline boundary sits in an awkward place.** With a remote detector, OCR
   still runs *client-side*, and the OCR text ensemble (ADR-016) injects a Python
   **callable** into the detector — which cannot cross gRPC. The workaround is the
   detector service's `--ocr` flag, i.e. the ensemble is *rebuilt on the service*.
   That duplication is a symptom: the orchestration seam cuts through a stage that
   wants to be whole.

"Orchestration service" can mean two very different things, and they deserve
opposite answers.

## Considered options

### Option A — Forwarding gateway

One endpoint that routes requests to detector / capture / actuator.

- ✗ **Duplicates the configuration.** `vizdom.config.json` already maps each port
  to a `host:port`; a gateway replaces one config file with one config file *plus a
  service to run*.
- ✗ **Adds a hop to the largest payload.** Screenshots are 1–2 MB. Today:
  capture → client → detector. Via a gateway: capture → gateway → client → gateway
  → detector — two extra transfers of the biggest thing on the wire, bought with
  indirection.
- ✗ **No physical locality.** Unlike the three existing services, a router has no
  reason to be anywhere in particular. It is distribution without a driver — the
  "microservices for their own sake" this project explicitly avoids (ADR-017).
- ✓ Single address to configure; one natural place to terminate TLS/auth (R-02).

The TLS/auth benefit is real but does not require orchestration: it belongs on
each service's channel.

### Option B — Session orchestrator (owns the pipeline)

Not forwarding: **hosting the domain**. The orchestrator holds the session, runs
capture → detect → OCR → merge → hierarchy → compile, keeps the DOM, and exposes a
*locator-level* API:

```
client:  dump()  ->  click("text=Save")  ->  verify("hint=Email", "user@example.com")
```

- ✓ **Removes the OCR seam.** The ensemble runs in the same process as the
  detector; `--ocr` and its silent-degradation footgun disappear.
- ✓ **Screenshot bytes never reach the client** — bandwidth, and the frame stays
  inside the SUT's network segment (relevant under a corporate proxy).
- ✓ **Coordinate geometry collapses to one machine.** The crop-origin /
  per-monitor-DPI / virtual-desktop corrections of ADR-021 exist because geometry
  crosses a process boundary; with the DOM server-side the client never handles a
  pixel.
- ✓ Enables clients that cannot host the pipeline at all (non-Python suites, thin
  CI containers, a phone).
- ✗ **It is the first *stateful* service.** "Which DOM belongs to which client"
  brings session ids, eviction, concurrency and staleness semantics (ADR-023's
  refresh model becomes a server concern) — a materially different class of
  component to operate and reason about than the three stateless ones.
- ✗ Must remain strictly optional or it breaks **NFR4** (the core runs end-to-end
  with no GPU and no network).
- ✗ A fourth process to start; the demo already asks for three terminals.

### Option C — Keep the client as the orchestrator (status quo)

- ✓ Zero new components; the in-process path stays the default and the test path.
- ✓ The client that orchestrates is also the client that *knows the test intent*,
  so staleness (ADR-023) and fallback-chain policy (ADR-024) live next to the code
  that decides them.
- ✗ Leaves the `--ocr` duplication in place.
- ✗ Each client re-implements orchestration if it is not Python.

## Decision

**Adopt Option C for now; record Option B as the intended shape when a driver
appears; reject Option A.**

Rationale, against the ranked drivers (arc42 Ch. 2): modifiability and
deployability are already satisfied — every port is swappable and remote-capable
by configuration, demonstrated end to end. Option B improves *deployability for
clients we do not yet have*, at the cost of the project's first stateful service.
With no such client in evidence, building it would be speculative generality, and
the ranked-driver method exists precisely to prevent that.

### Trigger conditions

Revisit — and implement Option B — when **any** of these becomes true:

1. **A non-Python client** must drive VizDOM (a Java/C# suite, or a CI runner that
   must not install torch/OpenCV).
2. **Several clients share one screen state** (parallel assertions against a single
   captured DOM), which needs a session that outlives one process.
3. **The client cannot host the pipeline** — a phone, a thin container, an embedded
   runner.
4. **The `--ocr` duplication turns into a defect source** rather than a documented
   footnote (e.g. a second callable-shaped extension point appears and needs the
   same workaround).

### If implemented, these constraints hold

- The orchestrator is an **inbound adapter** over the existing domain, not a new
  core: it must add no `core/` dependency and no new port (the fitness test in
  `tests/architecture/test_hexagon.py` guards this).
- **Explicit sessions**: `OpenSession(config) -> session_id`, idle timeout,
  explicit `CloseSession`; the DOM cache is per session, and ADR-023 staleness is
  reported to the client, never silently repaired.
- **Optional by construction**: in-process orchestration remains the default and
  the CI path.
- Security is designed in from the start (R-02), not retrofitted: a stateful
  service holding screenshots of an application under test is a materially larger
  exposure than a stateless detector.

## Consequences

**Positive**

- The orchestration question is answered explicitly, with the reasoning and the
  rejected option recorded — a reviewer can see *why* the client orchestrates.
- Trigger conditions make the future decision cheap: no re-litigation, just a
  check against the list.

**Negative**

- The `--ocr` duplication stays (documented in ADR-016 / USAGE).
- Non-Python clients remain unsupported; a future one pays the orchestrator cost
  at that point rather than now.
- A `Proposed` ADR that is never implemented can look like indecision; the trigger
  conditions are what distinguish deferral from drift.

## References

- ADR-016 OCR ensemble (the callable that cannot cross gRPC — the seam)
- ADR-017 Distributed hexagonal architecture with gRPC (physical-locality principle)
- ADR-018 / ADR-019 Pluggable capture / actuation (the stateless services)
- ADR-020 Client session configuration (`connect()` — where the session lives today)
- ADR-021 Application targeting and focus (the geometry that crosses the boundary)
- ADR-023 Post-action recap (staleness semantics that would become server-side)
- Risks register R-02 (unauthenticated channels), D-04 (no integration tests)
