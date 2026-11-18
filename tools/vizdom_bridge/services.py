"""
Start, stop and health-check the three gRPC services (ADR-017/018/019).

Same rules as the Viewer's Services window (ADR-026): a service answering on
its port that this bridge did not start is ``external`` and cannot be stopped
from here, and every service the bridge started is stopped when it exits.
"""

import json
import os
import socket
import subprocess
import sys
import threading
from collections import deque
from typing import Callable, Dict, List, Optional

from .sessions import HOME, REPO

SERVICES = {
    "detector": ("Detector", "visual_dom.adapters.inbound.grpc.detector_server", 50051,
                 "The heavy model. Run it where the GPU is."),
    "capture": ("Capture", "visual_dom.adapters.inbound.grpc.capture_server", 50053,
                "Must run where the application under test is visible."),
    "actuator": ("Actuator", "visual_dom.adapters.inbound.grpc.actuator_server", 50054,
                 "Must run where the clicks should land."),
}


#: Per-service options, mirroring each server's argparse (detector_server.py,
#: capture_server.py, actuator_server.py). ``flag`` is the CLI switch; a value
#: equal to "" / None / False is left off the command line, so the server's own
#: default applies. ``when`` shows a field only for some values of another.
_OPTIONS_CACHE: Dict[str, List[dict]] = {}


def _options(key: str) -> List[dict]:
    if key not in _OPTIONS_CACHE:
        _OPTIONS_CACHE[key] = _build_options(key)
    return _OPTIONS_CACHE[key]


def _build_options(key: str) -> List[dict]:
    if key == "detector":
        return [
            {"name": "backend", "label": "Backend", "type": "select", "flag": "--backend",
             "default": "modular",
             "choices": [["modular", "modular: boxes + OCR + roles"], ["omniparser", "omniparser"],
                         ["uied", "uied: classic CV"], ["yolo", "yolo: trained model"]],
             "help": "The model this service keeps warm for every client."},
            {"name": "captioner", "label": "Captioner", "type": "select", "flag": "--captioner",
             "default": "none", "when": {"backend": ["modular"]},
             "choices": [["none", "none"], ["ocr", "ocr: caption icons from text"],
                         ["florence", "florence: caption model (~1 GB VRAM)"]],
             "help": "Stage 3 of the modular detector."},
            {"name": "regions", "label": "Region proposer", "type": "select", "flag": "--regions",
             "default": "auto", "when": {"backend": ["modular"]},
             "choices": [["auto", "auto"], ["omniparser", "omniparser"], ["uied", "uied"]]},
            {"name": "ocr", "label": "OCR on the service", "type": "select", "flag": "--ocr",
             "default": "",
             "choices": [["", "server default"], ["easyocr", "easyocr"], ["paddleocr", "paddleocr"],
                         ["tesseract", "tesseract"], ["none", "none"]],
             "help": "Text is read where the detector runs; 'none' disables OCR for every backend."},
            {"name": "box_threshold", "label": "Box threshold", "type": "number", "flag": "--box-threshold",
             "default": "", "placeholder": "0.05", "when": {"backend": ["omniparser", "modular"]},
             "help": "OmniParser confidence cutoff; ~0.03 recovers faint glyphs."},
            {"name": "gpu", "label": "Use the GPU", "type": "bool", "flag": "--no-gpu", "invert": True,
             "default": True},
            {"name": "yolo_model", "label": "YOLO model", "type": "text", "flag": "--yolo-model",
             "default": "", "when": {"backend": ["yolo"]}, "placeholder": "path to .pt"},
            {"name": "icon_detect", "label": "Icon detector weights", "type": "text", "flag": "--icon-detect",
             "default": "", "advanced": True, "placeholder": "auto (models/omniparser)"},
            {"name": "icon_caption", "label": "Icon caption model", "type": "text", "flag": "--icon-caption",
             "default": "", "advanced": True, "placeholder": "auto (models/omniparser)"},
        ]
    registry = "capture" if key == "capture" else "actuator"
    try:
        if registry == "capture":
            from visual_dom.adapters.outbound.capture import list_captures as lister
        else:
            from visual_dom.adapters.outbound.actuator import list_actuators as lister
        choices = [["", "automatic for this OS"]] + [
            [s["name"], s["name"] + ("" if s["available"] else " (not available)")]
            for s in lister() if s["name"] != "grpc"]       # a service relaying to a service
    except Exception:  # noqa: BLE001
        choices = [["", "automatic for this OS"]]
    return [
        {"name": "strategy", "label": "Strategy", "type": "select", "flag": "--strategy",
         "default": "", "choices": choices,
         "help": "How this machine " + ("grabs the screen." if key == "capture" else "delivers input.")},
        {"name": "window_title", "label": "Default window", "type": "text", "flag": "--window-title",
         "default": "", "placeholder": "raised when a client sends no title",
         "help": "Android: package or package/.Activity."},
        {"name": "serial", "label": "Android serial", "type": "text", "flag": "--serial",
         "default": "", "when": {"strategy": ["android"]}, "placeholder": "adb -s"},
        {"name": "kw", "label": "Strategy arguments", "type": "lines", "flag": "--kw",
         "default": "", "advanced": True, "placeholder": "key=value, one per line",
         "help": "Passed to the strategy's constructor (plugins, camera index...)."},
    ]


def _visible(opt: dict, values: Dict[str, object]) -> bool:
    when = opt.get("when")
    return not when or all(values.get(k) in v for k, v in when.items())


def build_args(key: str, values: Dict[str, object]) -> List[str]:
    """The service's command-line options from the form values."""
    args: List[str] = []
    for opt in _options(key):
        if not _visible(opt, values):
            continue
        v = values.get(opt["name"], opt.get("default"))
        if opt["type"] == "bool":
            on = bool(v)
            if opt.get("invert"):
                on = not on
            if on:
                args.append(opt["flag"])
        elif opt["type"] == "lines":
            for line in str(v or "").splitlines():
                if line.strip():
                    args += [opt["flag"], line.strip()]
        elif v not in (None, ""):
            if opt["type"] == "number":
                float(v)                       # refuse garbage before the server does
            args += [opt["flag"], str(v)]
    return args


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.25):
            return True
    except (OSError, ValueError):
        return False


def health(key: str, port: int):
    """(ready, detail) through the service's own HealthCheck RPC."""
    if not _port_open(port):
        return False, "not reachable"
    try:
        import grpc
        if key == "detector":
            from visual_dom.generated import detector_pb2 as pb, detector_pb2_grpc as pbg
            stub_cls, request = pbg.DetectorStub, pb.HealthRequest()
        elif key == "capture":
            from visual_dom.generated import capture_pb2 as pb, capture_pb2_grpc as pbg
            stub_cls, request = pbg.CaptureStub, pb.HealthRequest()
        else:
            from visual_dom.generated import actuator_pb2 as pb, actuator_pb2_grpc as pbg
            stub_cls, request = pbg.ActuatorStub, pb.HealthRequest()
        channel = grpc.insecure_channel(f"localhost:{port}")
        try:
            response = stub_cls(channel).HealthCheck(request, timeout=1.0)
        finally:
            channel.close()
        if not getattr(response, "ready", False):
            return False, "not ready"
        label = (getattr(response, "backend", "") or getattr(response, "strategy", "")
                 or getattr(response, "actuator", "") or "ready")
        return True, label
    except ImportError:
        return False, "grpc not installed"
    except Exception:  # noqa: BLE001
        return False, "not reachable"


PREFS = HOME / "output" / ".studio" / "services.json"


class ServiceManager:
    def __init__(self, emit: Callable[[dict], None]):
        self._emit = emit
        self._procs: Dict[str, subprocess.Popen] = {}
        self._ports: Dict[str, int] = {k: v[2] for k, v in SERVICES.items()}
        self._logs: Dict[str, deque] = {k: deque(maxlen=400) for k in SERVICES}
        self._lock = threading.Lock()
        # last options used per service (remembered across launches), and the
        # options the running process was started with
        self._values: Dict[str, Dict[str, object]] = {k: {} for k in SERVICES}
        self._running_values: Dict[str, Dict[str, object]] = {}
        self._commands: Dict[str, List[str]] = {}
        try:
            saved = json.loads(PREFS.read_text(encoding="utf-8"))
            for k in SERVICES:
                self._values[k].update(saved.get(k, {}).get("values", {}))
                if saved.get(k, {}).get("port"):
                    self._ports[k] = int(saved[k]["port"])
        except (OSError, ValueError):
            pass

    def _save_prefs(self) -> None:
        try:
            PREFS.parent.mkdir(parents=True, exist_ok=True)
            PREFS.write_text(json.dumps({k: {"values": self._values[k], "port": self._ports[k]}
                                         for k in SERVICES}, indent=2), encoding="utf-8")
        except OSError:
            pass

    def values(self, key: str) -> Dict[str, object]:
        vals = {o["name"]: o.get("default") for o in _options(key)}
        vals.update(self._values.get(key, {}))
        return vals

    def _owned(self, key: str) -> Optional[subprocess.Popen]:
        proc = self._procs.get(key)
        if proc is not None and proc.poll() is not None:
            self._procs.pop(key, None)
            return None
        return proc

    def status(self) -> List[dict]:
        out = []
        for key, (title, module, default_port, hint) in SERVICES.items():
            port = self._ports[key]
            ready, detail = health(key, port)
            owned = self._owned(key) is not None
            if owned:
                state = "running" if ready else "starting"
            else:
                state = "external" if ready else "stopped"
            values = self.values(key)
            try:
                preview = build_args(key, values)
            except ValueError:
                preview = []
            out.append({"key": key, "title": title, "module": module, "port": port,
                        "default_port": default_port, "hint": hint, "state": state,
                        "ready": ready, "detail": detail, "owned": owned,
                        "options": _options(key), "values": values,
                        "running_values": self._running_values.get(key) if owned else None,
                        "command": self._commands.get(key) if owned else
                        ["python", "-m", module, "--port", str(port)] + preview,
                        "log": list(self._logs[key])[-200:]})
        return out

    def _log(self, key: str, line: str) -> None:
        self._logs[key].append(line)
        self._emit({"type": "service-log", "key": key, "line": line})

    def clear_log(self, key: str) -> None:
        """Forget the output kept for one service (the GUI's Clear button)."""
        if key not in self._logs:
            raise RuntimeError(f"Unknown service {key!r}")
        self._logs[key].clear()

    def set_values(self, key: str, values: Dict[str, object], port: Optional[int] = None) -> None:
        """Remember the form without starting anything."""
        if key not in SERVICES:
            raise KeyError(key)
        known = {o["name"] for o in _options(key)}
        self._values[key] = {k: v for k, v in (values or {}).items() if k in known}
        if port and self._owned(key) is None:
            self._ports[key] = int(port)
        self._save_prefs()

    def start(self, key: str, port: Optional[int] = None,
              values: Optional[Dict[str, object]] = None) -> None:
        if key not in SERVICES:
            raise KeyError(key)
        if values is not None:
            self.set_values(key, values, port)
        vals = self.values(key)
        try:
            extra = build_args(key, vals)
        except ValueError as exc:
            raise RuntimeError(f"invalid option: {exc}")
        with self._lock:
            if self._owned(key) is not None:
                return
            if port:
                self._ports[key] = int(port)
            if _port_open(self._ports[key]):
                raise RuntimeError(f"port {self._ports[key]} is already in use "
                                   "(a service started elsewhere?)")
            env = dict(os.environ)
            env["PYTHONPATH"] = os.pathsep.join(
                [str(REPO / "src"), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
            env["PYTHONUNBUFFERED"] = "1"
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            cmd = ["-m", SERVICES[key][1], "--port", str(self._ports[key])] + extra
            proc = subprocess.Popen(
                [sys.executable] + cmd,
                cwd=str(HOME), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", creationflags=flags)
            self._procs[key] = proc
            self._running_values[key] = dict(vals)
            self._commands[key] = ["python"] + cmd
            self._save_prefs()
        self._log(key, "$ python " + " ".join(cmd))

        def pump():
            for line in proc.stdout:
                self._log(key, line.rstrip())
            self._log(key, f"[exited with code {proc.wait()}]")
            self._emit({"type": "services-changed"})

        threading.Thread(target=pump, name=f"svc-{key}", daemon=True).start()
        self._emit({"type": "services-changed"})

    def stop(self, key: str) -> None:
        proc = self._owned(key)
        if proc is None:
            raise RuntimeError("this service was not started here, so it is not stopped here")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        self._emit({"type": "services-changed"})

    def shutdown(self) -> None:
        for key in list(self._procs):
            try:
                self.stop(key)
            except Exception:  # noqa: BLE001
                pass
