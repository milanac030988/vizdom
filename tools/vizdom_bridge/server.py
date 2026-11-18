"""
HTTP + WebSocket API of the VizDOM Studio bridge.

Long work (capture + analysis, a locator trial) runs as a *job* on one worker
thread - one at a time, as in the Viewer, where queued presses once nested
analyses until the stack overflowed. Job progress and service logs are pushed
on ``/api/events``; everything else is plain request/response.

Every request carries the launch token (``X-VizDOM-Token`` header, or
``?token=`` for <img> and WebSocket URLs); the server binds 127.0.0.1 only.
"""

import asyncio
import json
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from .sessions import HOME, REPO

for _p in (REPO / "src", REPO / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402

from . import sessions as S  # noqa: E402
from .services import ServiceManager  # noqa: E402


class BridgeState:
    def __init__(self, token: str, config_path: Optional[str]):
        from visual_dom.config import VizDomConfig
        self.token = token
        default = HOME / "vizdom.config.json"
        self.config_path = Path(config_path) if config_path else default
        source = str(self.config_path) if self.config_path.exists() else None
        self.config: Dict[str, Any] = VizDomConfig.load(source).to_dict()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.sockets: set = set()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vizdom-job")
        self.job: Optional[Dict[str, Any]] = None
        self.job_lock = threading.Lock()
        self.sessions_cache: Dict[str, Any] = {}       # config json -> visual_dom Session
        self.services = ServiceManager(self.emit)
        self.actuation_confirmed = False

    # ---- events --------------------------------------------------------- #
    def emit(self, event: Dict[str, Any]) -> None:
        """Thread-safe broadcast to every connected GUI window."""
        loop = self.loop
        if loop is None or not self.sockets:
            return
        text = json.dumps(event, default=str)

        async def send():
            for ws in list(self.sockets):
                try:
                    await ws.send_text(text)
                except Exception:  # noqa: BLE001 - a closed window
                    self.sockets.discard(ws)

        try:
            asyncio.run_coroutine_threadsafe(send(), loop)
        except RuntimeError:
            pass

    # ---- jobs ----------------------------------------------------------- #
    def start_job(self, kind: str, fn, **meta) -> Dict[str, Any]:
        with self.job_lock:
            if self.job and self.job["state"] == "running":
                raise HTTPException(409, f"Busy: {self.job['title']} is still running")
            job = {"id": uuid.uuid4().hex[:8], "kind": kind, "state": "running",
                   "title": meta.get("title", kind), "stage": "queued", "progress": 0,
                   "message": "", "result": None, "error": None, "started": time.time()}
            self.job = job

        def update(stage: str, progress: int, message: str = "") -> None:
            job.update(stage=stage, progress=progress, message=message)
            self.emit({"type": "job", "job": _public(job)})

        def run():
            try:
                job["result"] = fn(update)
                job["state"] = "done"
                job["progress"] = 100
            except Exception as exc:  # noqa: BLE001 - reported to the GUI
                traceback.print_exc()
                job["state"] = "error"
                job["error"] = f"{type(exc).__name__}: {exc}" if not isinstance(exc, UserError) else str(exc)
            job["elapsed"] = round(time.time() - job["started"], 2)
            self.emit({"type": "job", "job": _public(job)})

        self.emit({"type": "job", "job": _public(job)})
        self.executor.submit(run)
        return _public(job)

    # ---- the pipeline --------------------------------------------------- #
    def session_for_config(self, update) -> Any:
        from visual_dom import connect
        key = json.dumps(self.config, sort_keys=True)
        if key not in self.sessions_cache:
            det = self.config.get("detector", {}).get("backend")
            update("models", 25, f"Loading models ({det}) - first run takes a while")
            self.sessions_cache.clear()          # one warm pipeline is enough memory
            self.sessions_cache[key] = connect(dict(self.config))
        return self.sessions_cache[key]

    def analyze(self, png: bytes, context: Dict[str, Any], update) -> Dict[str, Any]:
        import cv2
        import numpy as np
        img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise UserError("The image could not be decoded")
        session = self.session_for_config(update)
        update("analyze", 60, "Detecting elements and reading text")
        t0 = time.time()
        dom = session.analyze(img)
        update("save", 92, "Saving the session")
        path = S.new_session_dir()
        cfg = self.config
        info = dict(context)
        info.update({
            "detector": cfg.get("detector", {}).get("backend"),
            "ocr_engine": cfg.get("ocr", {}).get("engine"),
            "camera_mode": cfg.get("capture", {}).get("camera_mode"),
            "slm_enabled": cfg.get("refiner", {}).get("enabled"),
            "analysis_seconds": round(time.time() - t0, 2),
            "cv_stats": {"detector": cfg.get("detector", {}).get("backend"),
                         "final_count": len(dom.get("elements") or [])},
        })
        S.write_session(path, png, dom, info)
        return {"session_id": path.name, "element_count": len(dom.get("elements") or [])}

    def capture_png(self, strategy: Optional[str], title: Optional[str],
                    kwargs: Optional[Dict[str, Any]] = None):
        """One frame through a capture strategy (ADR-018/021): (png, provenance)."""
        import cv2
        from visual_dom.adapters.outbound.capture import auto_select, create_capture
        name = strategy or self.config.get("capture", {}).get("strategy") or auto_select()
        if not name:
            raise UserError("No capture strategy is available on this machine")
        kwargs = dict(kwargs or {})
        if name == "grpc" and self.config.get("capture", {}).get("target") and "target" not in kwargs:
            kwargs["target"] = self.config["capture"]["target"]
        cap = create_capture(name, **kwargs)
        context: Dict[str, Any] = {}
        try:
            try:
                context.update(cap.describe_target() or {})
            except Exception:  # noqa: BLE001
                pass
            context["capture_source"] = f"strategy:{name}"
            captured = None
            if title:
                try:
                    captured = cap.capture_window(title)
                except Exception:  # noqa: BLE001 - fall back to the full screen
                    captured = None
                if captured is None:
                    try:
                        cap.focus_target(title)
                        time.sleep(0.4)
                    except Exception:  # noqa: BLE001
                        pass
            if captured is not None:
                frame = captured.image
                context.update({
                    "capture_scope": "window",
                    "window_title": captured.window_title or title,
                    "capture_origin": list(captured.origin),
                    "device_origin": list(captured.device_origin),
                    "device_size": list(captured.device_size),
                })
            else:
                frame = cap.capture()
                context["capture_scope"] = "screen"
                if title:
                    context["window_title"] = title
                try:
                    geometry = cap.frame_geometry()
                except Exception:  # noqa: BLE001
                    geometry = None
                if geometry:
                    origin, device_origin, device_size = geometry
                    context.update({"capture_origin": list(origin),
                                    "device_origin": list(device_origin),
                                    "device_size": list(device_size)})
        finally:
            try:
                cap.close()
            except Exception:  # noqa: BLE001
                pass
        if frame is None:
            raise UserError(f"Capture via '{name}' returned no frame")
        ok, buf = cv2.imencode(".png", frame)
        if not ok:
            raise UserError("The captured frame could not be encoded")
        return buf.tobytes(), context

    def grounding(self):
        from visual_dom.config import VizDomConfig
        try:
            return VizDomConfig.load(dict(self.config)).grounding
        except Exception:  # noqa: BLE001
            return None


class UserError(RuntimeError):
    """An error whose message is meant for the user as it is."""


def _public(job: Dict[str, Any]) -> Dict[str, Any]:
    return {k: job.get(k) for k in ("id", "kind", "state", "title", "stage", "progress",
                                    "message", "result", "error", "elapsed")}


def _set_path(data: Dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = data
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def create_app(token: str = "", config_path: Optional[str] = None) -> FastAPI:
    state = BridgeState(token, config_path)

    @asynccontextmanager
    async def lifespan(_app):
        state.loop = asyncio.get_running_loop()
        try:
            yield
        finally:
            state.services.shutdown()

    app = FastAPI(title="VizDOM Studio bridge", docs_url=None, redoc_url=None,
                  lifespan=lifespan)
    app.state.bridge = state
    # Renderer origin is file:// (packaged) or the Vite dev server; the token is
    # what protects the API, so any origin may call it with the token.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])

    @app.middleware("http")
    async def check_token(request: Request, call_next):
        if request.method != "OPTIONS" and state.token:
            given = request.headers.get("x-vizdom-token") or request.query_params.get("token")
            if given != state.token:
                return JSONResponse({"detail": "bad token"}, status_code=401)
        return await call_next(request)

    # ---- basics ---------------------------------------------------------- #
    @app.get("/api/health")
    def health():
        return {"ok": True, "repo": str(REPO), "python": sys.version.split()[0],
                "job": _public(state.job) if state.job else None}

    @app.websocket("/api/events")
    async def events(ws: WebSocket):
        if state.token and ws.query_params.get("token") != state.token:
            await ws.close(code=4401)
            return
        await ws.accept()
        state.sockets.add(ws)
        try:
            while True:
                await ws.receive_text()      # keep-alive pings from the GUI
        except WebSocketDisconnect:
            pass
        finally:
            state.sockets.discard(ws)

    @app.post("/api/shutdown")
    def shutdown():
        """Stop the services this bridge started. The GUI calls it before ending
        the bridge, because a killed process on Windows runs no cleanup."""
        state.services.shutdown()
        return {"ok": True}

    @app.get("/api/jobs/current")
    def current_job():
        return _public(state.job) if state.job else None

    # ---- config ---------------------------------------------------------- #
    def config_payload():
        c = state.config
        return {
            "path": str(state.config_path),
            "exists": state.config_path.exists(),
            "config": c,
            "summary": {
                "detector": c.get("detector", {}).get("backend"),
                "ocr": c.get("ocr", {}).get("engine"),
                "refiner": c.get("refiner", {}).get("model") if c.get("refiner", {}).get("enabled") else None,
                "capture": c.get("capture", {}).get("strategy") or "auto",
                "tiers": c.get("grounding", {}).get("tiers"),
            },
        }

    @app.get("/api/config")
    def get_config():
        return config_payload()

    @app.patch("/api/config")
    def patch_config(changes: Dict[str, Any] = Body(...)):
        """``{"detector.backend": "modular", ...}``; validated by VizDomConfig itself."""
        from visual_dom.config import VizDomConfig
        candidate = json.loads(json.dumps(state.config))
        for key, value in changes.items():
            _set_path(candidate, key, value)
        try:
            state.config = VizDomConfig.load(candidate).to_dict()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"Invalid setting: {exc}")
        return config_payload()

    @app.post("/api/config/save")
    def save_config(body: Dict[str, Any] = Body(default={})):
        """Save to the current file, or to ``path`` (Save As), which becomes current."""
        from visual_dom.config import VizDomConfig
        target = Path(body["path"]) if body.get("path") else state.config_path
        try:
            VizDomConfig.load(dict(state.config)).save(target)
        except OSError as exc:
            raise HTTPException(400, f"Could not write {target}: {exc}")
        state.config_path = target
        return config_payload()

    @app.post("/api/config/load")
    def load_config(body: Dict[str, Any] = Body(...)):
        """Use another session config file; validated by VizDomConfig.load itself."""
        from visual_dom.config import VizDomConfig
        path = Path(body.get("path") or "")
        if not path.is_file():
            raise HTTPException(400, f"No such file: {path}")
        try:
            config = VizDomConfig.load(str(path)).to_dict()
        except Exception as exc:  # noqa: BLE001 - unknown keys, bad JSON, bad values
            raise HTTPException(400, f"{path.name} is not a valid VizDOM config: {exc}")
        state.config_path = path
        state.config = config
        return config_payload()

    @app.post("/api/config/reload")
    def reload_config():
        from visual_dom.config import VizDomConfig
        source = str(state.config_path) if state.config_path.exists() else None
        state.config = VizDomConfig.load(source).to_dict()
        return config_payload()

    # ---- targets --------------------------------------------------------- #
    @app.get("/api/windows")
    def windows():
        try:
            from visual_dom.adapters.outbound import win32_window as w
            if not w.is_windows():
                return []
            seen, out = set(), []
            for _hwnd, title in w.list_windows():
                t = (title or "").strip()
                if t and t not in seen and t not in ("Program Manager",):
                    seen.add(t)
                    out.append(t)
            return out
        except Exception:  # noqa: BLE001
            return []

    @app.get("/api/strategies")
    def strategies():
        from visual_dom.adapters.outbound.actuator import list_actuators
        from visual_dom.adapters.outbound.capture import auto_select, list_captures
        return {"capture": list_captures(), "capture_default": auto_select(),
                "actuator": list_actuators()}

    # ---- analysis jobs ----------------------------------------------------- #
    @app.post("/api/capture")
    def capture(body: Dict[str, Any] = Body(default={})):
        """
        Grab the frame NOW (the GUI hides its window around this call), then
        analyse it as a job.
        """
        if state.job and state.job["state"] == "running":
            raise HTTPException(409, f"Busy: {state.job['title']} is still running")
        title = (body.get("window_title") or "").strip() or None
        try:
            png, context = state.capture_png(body.get("strategy"), title, body.get("kwargs"))
        except UserError as exc:
            raise HTTPException(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, f"Capture failed: {type(exc).__name__}: {exc}")
        label = context.get("window_title") or "screen"
        return state.start_job("analyze", lambda up: state.analyze(png, context, up),
                               title=f"Analyze {label}")

    @app.post("/api/analyze-file")
    def analyze_file(body: Dict[str, Any] = Body(...)):
        path = Path(body.get("path") or "")
        if not path.is_file():
            raise HTTPException(400, f"No such image: {path}")
        png = _to_png(path.read_bytes())
        context = {"capture_source": "file", "source_file": str(path)}
        return state.start_job("analyze", lambda up: state.analyze(png, context, up),
                               title=f"Analyze {path.name}")

    @app.post("/api/sessions/{session_id}/reanalyze")
    def reanalyze(session_id: str):
        try:
            path = S.session_dir(session_id)
        except KeyError:
            raise HTTPException(404, "No such session")
        shot = path / "screenshot.png"
        if not shot.exists():
            raise HTTPException(400, "This session has no screenshot to analyse")
        png = shot.read_bytes()
        context = {k: v for k, v in S.load_info(session_id).items()
                   if k in ("capture_source", "capture_scope", "window_title", "process_name",
                            "capture_origin", "device_origin", "device_size", "source_file")}
        context["reanalyzed_from"] = session_id
        return state.start_job("analyze", lambda up: state.analyze(png, context, up),
                               title=f"Re-analyze {session_id}")

    @app.post("/api/import-dom")
    def import_dom(body: Dict[str, Any] = Body(...)):
        try:
            return {"session_id": S.import_dom_file(Path(body.get("path") or ""))}
        except (OSError, ValueError) as exc:
            raise HTTPException(400, str(exc))

    # ---- sessions --------------------------------------------------------- #
    @app.get("/api/sessions")
    def sessions(limit: int = 200):
        return S.list_sessions(limit)

    @app.get("/api/sessions/{session_id}")
    def session(session_id: str):
        try:
            return S.session_view(session_id)
        except KeyError:
            raise HTTPException(404, "No such session")

    @app.get("/api/sessions/{session_id}/screenshot")
    def screenshot(session_id: str):
        try:
            path = S.session_dir(session_id) / "screenshot.png"
        except KeyError:
            raise HTTPException(404, "No such session")
        if not path.exists():
            raise HTTPException(404, "No screenshot")
        return FileResponse(path, media_type="image/png",
                            headers={"Cache-Control": "max-age=3600"})

    # ---- locators --------------------------------------------------------- #
    @app.post("/api/sessions/{session_id}/resolve")
    def resolve(session_id: str, body: Dict[str, Any] = Body(...)):
        """
        Resolve a locator exactly as a suite would (``LocatorResolver.explain``),
        and list what each alternative matches, so the GUI can highlight them.
        """
        locator = (body.get("locator") or "").strip()
        if not locator:
            raise HTTPException(400, "Empty locator")
        try:
            data = S.load_result(session_id)
        except KeyError:
            raise HTTPException(404, "No such session")
        dom = data["dom"]
        from visual_gui_library.locators import LocatorResolver
        from visual_gui_library.locators.locator import ElementFinder, LocatorParser, LocatorStrategy
        alternatives = LocatorParser.parse_alternatives(locator)
        if not alternatives:
            return {"ok": False, "error": f"Could not parse locator: {locator!r}",
                    "alternatives": [], "element_id": None}
        finder = ElementFinder(dom)
        alts = []
        for group in alternatives:
            rendered = LocatorParser.render(group)
            uses_desc = any(l.strategy == LocatorStrategy.DESC for l in group)
            matches: List[str] = []
            if not uses_desc:
                try:
                    matches = [e.get("id") for e in finder.find(group)]
                except Exception:  # noqa: BLE001
                    matches = []
            alts.append({"rendered": rendered, "matches": matches, "uses_model": uses_desc})
        use_models = bool(body.get("allow_models", True))
        has_desc = any(a["uses_model"] for a in alts)
        if has_desc and not use_models:
            return {"ok": False, "element_id": None, "alternatives": alts,
                    "error": "desc= needs the grounding models; resolve it explicitly"}
        screenshot = None
        if has_desc:
            try:
                import cv2
                screenshot = cv2.imread(str(S.session_dir(session_id) / "screenshot.png"))
            except Exception:  # noqa: BLE001
                screenshot = None
        t0 = time.time()
        res = LocatorResolver.for_dom(dom, screenshot, state.grounding() if has_desc else None).explain(locator)
        return {
            "ok": res.ok,
            "element_id": res.element.get("id") if res.element else None,
            "alternative": res.alternative,
            "rendered": res.rendered,
            "used_fallback": res.used_fallback if res.ok else False,
            "attempts": [{"rendered": r, "why": why} for r, why in res.attempts],
            "error": None if res.ok else res.error_message(),
            "alternatives": alts,
            "seconds": round(time.time() - t0, 3),
        }

    # ---- export ------------------------------------------------------------ #
    def _tree_and_elements(session_id: str, ids: Optional[List[str]]):
        from visual_dom_viewer.core.tree import DOMTree
        data = S.load_result(session_id)
        tree = DOMTree.from_dict(data)
        wanted = ids or [e["id"] for e in data["dom"].get("elements") or []]
        elements = [tree.get_element_by_id(i) for i in wanted]
        return tree, [e for e in elements if e is not None]

    @app.post("/api/sessions/{session_id}/export")
    def export(session_id: str, body: Dict[str, Any] = Body(default={})):
        from visual_dom_viewer.export.robot_exporter import RobotResourceExporter
        try:
            tree, elements = _tree_and_elements(session_id, body.get("element_ids"))
        except KeyError:
            raise HTTPException(404, "No such session")
        if not elements:
            raise HTTPException(400, "No elements to export")
        exporter = RobotResourceExporter()
        if body.get("naming") in ("text_first", "type_first", "id_only"):
            exporter.set_naming_strategy(body["naming"])
        title = body.get("title") or "UI Elements"
        path = body.get("path")
        if not path:
            return {"content": exporter.preview(elements), "path": None, "count": len(elements)}
        if not exporter.export(elements, path, dom_tree=tree, title=title):
            raise HTTPException(500, "Export failed")
        return {"content": Path(path).read_text(encoding="utf-8"), "path": path,
                "count": len(elements)}

    # ---- try a locator through the actuator (ADR-028) ---------------------- #
    @app.post("/api/sessions/{session_id}/try")
    def try_locator(session_id: str, body: Dict[str, Any] = Body(...)):
        from visual_dom_viewer.core.actuation import ActuationError, ActuationSettings, LocatorTrial
        locator = (body.get("locator") or "").strip()
        if not locator:
            raise HTTPException(400, "Empty locator")
        click_type = body.get("click_type") or "single"
        try:
            info = S.load_info(session_id)
            S.load_result(session_id)
        except KeyError:
            raise HTTPException(404, "No such session")
        title = (body.get("window_title") or "").strip() or info.get("window_title")
        if not title:
            raise HTTPException(400, "No target window: set one in the toolbar so it can be "
                                     "raised before the click")
        act_cfg = state.config.get("actuator", {})
        settings = ActuationSettings(strategy=body.get("actuator") or act_cfg.get("strategy"),
                                     target=body.get("actuator_target") or act_cfg.get("target"),
                                     window_title=title)

        def run(update):
            sid = session_id
            if body.get("recapture_before", True):
                update("capture", 10, "Capturing again before resolving (what the test will see)")
                png, context = state.capture_png(None, title)
                sid = state.analyze(png, context, update)["session_id"]
            data = S.load_result(sid)
            ctx = S.load_info(sid)
            size = data.get("image_size") or {}
            image_size = (size.get("width"), size.get("height")) if size.get("width") else None
            actuator = settings.create_actuator()
            try:
                update("click", 85, f"Resolving and clicking via {actuator.name}")
                import cv2
                shot = cv2.imread(str(S.session_dir(sid) / "screenshot.png"))
                trial = LocatorTrial(actuator, settle=lambda: time.sleep(0.3))
                try:
                    outcome = trial.run(locator, data["dom"], ctx, image_size, title,
                                        click_type=click_type, screenshot=shot,
                                        grounding=state.grounding())
                except ActuationError as exc:
                    raise UserError(str(exc))
            finally:
                try:
                    actuator.close()
                except Exception:  # noqa: BLE001
                    pass
            result = {"session_id": sid, "clicked": outcome.clicked,
                      "element_id": outcome.element_id, "locator": locator,
                      "actuator": actuator.name,
                      "point": list(outcome.point) if outcome.point else None,
                      "focused_via": outcome.focused_via, "notes": outcome.notes,
                      "error": None if outcome.clicked else outcome.resolution.error_message()}
            if outcome.clicked and body.get("recapture_after", True):
                time.sleep(0.8)
                update("capture", 90, "Capturing the result of the click")
                png, context = state.capture_png(None, title)
                result["after_session_id"] = state.analyze(png, context, update)["session_id"]
            return result

        return state.start_job("try", run, title=f"Try {locator}")

    # ---- services ----------------------------------------------------------- #
    @app.get("/api/services")
    def services():
        return state.services.status()

    @app.post("/api/services/{key}/start")
    def service_start(key: str, body: Dict[str, Any] = Body(default={})):
        try:
            state.services.start(key, body.get("port"), body.get("values"))
        except KeyError:
            raise HTTPException(404, "No such service")
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))
        return state.services.status()

    @app.put("/api/services/{key}/options")
    def service_options(key: str, body: Dict[str, Any] = Body(default={})):
        try:
            state.services.set_values(key, body.get("values") or {}, body.get("port"))
        except KeyError:
            raise HTTPException(404, "No such service")
        return state.services.status()

    @app.post("/api/services/{key}/use")
    def service_use(key: str, body: Dict[str, Any] = Body(default={})):
        """Point the session config at this service (detector / capture / actuator = grpc)."""
        from visual_dom.config import VizDomConfig
        target = body.get("target") or f"localhost:{body.get('port')}"
        changes = {
            "detector": {"detector.backend": "grpc", "detector.grpc_target": target},
            "capture": {"capture.strategy": "grpc", "capture.target": target},
            "actuator": {"actuator.strategy": "grpc", "actuator.target": target},
        }.get(key)
        if changes is None:
            raise HTTPException(404, "No such service")
        candidate = json.loads(json.dumps(state.config))
        for k, v in changes.items():
            _set_path(candidate, k, v)
        state.config = VizDomConfig.load(candidate).to_dict()
        return config_payload()

    @app.post("/api/services/{key}/stop")
    def service_stop(key: str):
        try:
            state.services.stop(key)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))
        return state.services.status()

    @app.delete("/api/services/{key}/log")
    def service_clear_log(key: str):
        try:
            state.services.clear_log(key)
        except RuntimeError as exc:
            raise HTTPException(404, str(exc))
        return state.services.status()

    return app


def _to_png(raw: bytes) -> bytes:
    """Any image file the GUI opens -> PNG bytes (sessions always hold a PNG)."""
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return raw
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "The file is not an image VizDOM can read")
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()
