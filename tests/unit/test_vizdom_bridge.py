"""The VizDOM Studio bridge: token, sessions, locators, export, config (no models)."""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from vizdom_bridge import sessions as S  # noqa: E402
from vizdom_bridge.server import create_app  # noqa: E402

TOKEN = "t0ken"

DOM = {
    "image_size": {"width": 200, "height": 100},
    "source": "test",
    "session_id": "x",
    "cv_stats": {},
    "dom": {
        "version": "1.0",
        "image_size": [200, 100],
        "element_count": 3,
        "hierarchy": {"id": "ROOT", "bounds": [0, 0, 200, 100], "role": "root",
                      "visual_type": "container", "children": [
                          {"id": "E1", "bounds": [10, 10, 60, 30], "center": [35, 20],
                           "role": "button", "visual_type": "button", "text": "Save",
                           "label": "Save", "children": []},
                          {"id": "E2", "bounds": [70, 10, 120, 30], "center": [95, 20],
                           "role": "button", "visual_type": "button", "text": "Save As",
                           "label": "Save As", "children": []},
                          {"id": "E3", "bounds": [10, 50, 60, 70], "center": [35, 60],
                           "role": "staticText", "visual_type": "text", "text": "Save",
                           "label": "Save", "children": []}]},
        "elements": [
            {"id": "E1", "bounds": [10, 10, 60, 30], "center": [35, 20], "role": "button",
             "visual_type": "button", "clickable": True, "text": "Save", "label": "Save"},
            {"id": "E2", "bounds": [70, 10, 120, 30], "center": [95, 20], "role": "button",
             "visual_type": "button", "clickable": True, "text": "Save As", "label": "Save As"},
            {"id": "E3", "bounds": [10, 50, 60, 70], "center": [35, 60], "role": "staticText",
             "visual_type": "text", "clickable": False, "text": "Save", "label": "Save"},
        ],
    },
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "SESSIONS", tmp_path / "sessions")
    sid_dir = tmp_path / "sessions" / "20260101_000000"
    sid_dir.mkdir(parents=True)
    (sid_dir / "dom_result.json").write_text(json.dumps(DOM), encoding="utf-8")
    (sid_dir / "session_info.json").write_text(json.dumps({"element_count": 3}), encoding="utf-8")
    app = create_app(token=TOKEN, config_path=str(tmp_path / "vizdom.config.json"))
    with TestClient(app) as c:
        c.headers.update({"X-VizDOM-Token": TOKEN})
        yield c


def test_every_request_needs_the_token(client):
    assert client.get("/api/health", headers={"X-VizDOM-Token": "wrong"}).status_code == 401
    assert client.get("/api/health").json()["ok"] is True


def test_sessions_list_and_view_carry_the_exported_locator(client):
    listed = client.get("/api/sessions").json()
    assert [s["id"] for s in listed] == ["20260101_000000"]
    view = client.get("/api/sessions/20260101_000000").json()
    by_id = {e["id"]: e for e in view["elements"]}
    assert by_id["E1"]["locator"] == "text=Save role=button || id=E1"
    assert view["hierarchy"]["children"][0]["id"] == "E1"
    assert view["image"] == {"width": 200, "height": 100}


def test_session_ids_cannot_leave_the_sessions_folder(client):
    assert client.get("/api/sessions/..%5C..%5Cetc").status_code == 404


def test_resolve_reports_ambiguity_and_the_matches_to_highlight(client):
    r = client.post("/api/sessions/20260101_000000/resolve", json={"locator": "text=Save"}).json()
    assert r["ok"] is False
    assert set(r["alternatives"][0]["matches"]) == {"E1", "E3"}
    r = client.post("/api/sessions/20260101_000000/resolve",
                    json={"locator": "text=Save role=button || id=E1"}).json()
    assert r["ok"] is True and r["element_id"] == "E1" and r["alternative"] == 0


def test_export_preview_and_file(client, tmp_path):
    prev = client.post("/api/sessions/20260101_000000/export", json={"element_ids": ["E1"]}).json()
    assert prev["path"] is None and prev["count"] == 1 and "Save" in prev["content"]
    out = tmp_path / "ui.resource"
    saved = client.post("/api/sessions/20260101_000000/export",
                        json={"path": str(out), "title": "Demo"}).json()
    assert out.exists() and saved["count"] == 3 and "VisualGuiLibrary" in saved["content"]


def test_config_patch_is_validated_by_the_real_schema(client):
    ok = client.patch("/api/config", json={"detector.backend": "modular"}).json()
    assert ok["summary"]["detector"] == "modular"
    bad = client.patch("/api/config", json={"detector.no_such_field": 1})
    assert bad.status_code == 400


def test_config_files_load_and_save_as(client, tmp_path):
    good = tmp_path / "suite.config.json"
    good.write_text(json.dumps({"detector": {"backend": "omniparser"}, "ocr": {"engine": "tesseract"}}),
                    encoding="utf-8")
    cfg = client.post("/api/config/load", json={"path": str(good)}).json()
    assert cfg["path"] == str(good) and cfg["summary"]["detector"] == "omniparser"
    assert cfg["summary"]["ocr"] == "tesseract"

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"detector": {"no_such_key": 1}}), encoding="utf-8")
    r = client.post("/api/config/load", json={"path": str(bad)})
    assert r.status_code == 400 and "not a valid VizDOM config" in r.json()["detail"]
    assert client.get("/api/config").json()["path"] == str(good)      # unchanged on failure
    assert client.post("/api/config/load", json={"path": str(tmp_path / "nope.json")}).status_code == 400

    copy = tmp_path / "copy.json"
    saved = client.post("/api/config/save", json={"path": str(copy)}).json()
    assert saved["path"] == str(copy) and saved["exists"]
    assert json.loads(copy.read_text(encoding="utf-8"))["detector"]["backend"] == "omniparser"


def test_service_options_become_the_servers_command_line():
    from vizdom_bridge.services import build_args
    args = build_args("detector", {"backend": "modular", "captioner": "ocr", "regions": "auto",
                                   "ocr": "", "box_threshold": "0.03", "gpu": False,
                                   "yolo_model": "ignored.pt"})
    assert args == ["--backend", "modular", "--captioner", "ocr", "--regions", "auto",
                    "--box-threshold", "0.03", "--no-gpu"]          # yolo_model hidden for modular
    assert build_args("detector", {"backend": "uied", "gpu": True}) == ["--backend", "uied"]
    cap = build_args("capture", {"strategy": "android", "serial": "emu-5554",
                                 "window_title": "com.app", "kw": "a=1\n\n b=2 "})
    assert cap == ["--strategy", "android", "--window-title", "com.app", "--serial", "emu-5554",
                   "--kw", "a=1", "--kw", "b=2"]
    with pytest.raises(ValueError):
        build_args("detector", {"backend": "omniparser", "box_threshold": "abc"})


def test_service_options_are_listed_and_remembered(client, tmp_path, monkeypatch):
    import vizdom_bridge.services as svc
    monkeypatch.setattr(svc, "PREFS", tmp_path / "services.json")
    det = next(s for s in client.get("/api/services").json() if s["key"] == "detector")
    assert {o["name"] for o in det["options"]} >= {"backend", "captioner", "ocr", "gpu"}
    after = client.put("/api/services/detector/options",
                       json={"values": {"backend": "uied", "bogus": 1}, "port": 50061}).json()
    det = next(s for s in after if s["key"] == "detector")
    assert det["values"]["backend"] == "uied" and "bogus" not in det["values"]
    assert det["port"] == 50061 and "--backend uied" in " ".join(det["command"])


def test_service_log_can_be_cleared(client):
    from vizdom_bridge.services import ServiceManager
    events = []
    mgr = ServiceManager(events.append)
    mgr._log("detector", "line one")
    mgr._log("detector", "ERROR line two")
    assert len(events) == 2
    mgr.clear_log("detector")
    det = next(s for s in mgr.status() if s["key"] == "detector")
    assert det["log"] == []
    with pytest.raises(RuntimeError):
        mgr.clear_log("bogus")
    # the endpoint the GUI's Clear button calls
    after = client.delete("/api/services/detector/log")
    assert after.status_code == 200
    assert next(s for s in after.json() if s["key"] == "detector")["log"] == []
    assert client.delete("/api/services/bogus/log").status_code == 404


def test_use_service_points_the_config_at_it(client):
    cfg = client.post("/api/services/detector/use", json={"port": 50051}).json()
    assert cfg["config"]["detector"]["backend"] == "grpc"
    assert cfg["config"]["detector"]["grpc_target"] == "localhost:50051"
    cfg = client.post("/api/services/actuator/use", json={"port": 50054}).json()
    assert cfg["config"]["actuator"] == {**cfg["config"]["actuator"], "strategy": "grpc",
                                         "target": "localhost:50054"}


def test_import_dom_from_outside_copies_it_into_a_session(client, tmp_path):
    src = tmp_path / "elsewhere"
    src.mkdir()
    (src / "dom_result.json").write_text(json.dumps(DOM), encoding="utf-8")
    sid = client.post("/api/import-dom", json={"path": str(src / "dom_result.json")}).json()["session_id"]
    assert sid != "20260101_000000"
    assert client.get(f"/api/sessions/{sid}").status_code == 200


def test_installed_layout_keeps_user_data_apart_from_the_code(tmp_path):
    """The installed Studio sets VIZDOM_REPO (read-only resources) and VIZDOM_HOME
    (Documents/VizDOM): sessions and the config go to HOME, code is found in REPO."""
    import os
    import subprocess

    code, home = tmp_path / "resources", tmp_path / "home"
    env = {**os.environ, "VIZDOM_REPO": str(code), "VIZDOM_HOME": str(home),
           "PYTHONPATH": str(REPO / "tools")}
    out = subprocess.run(
        [sys.executable, "-c",
         "import json; from vizdom_bridge import sessions as s, services as v; "
         "print(json.dumps([str(s.REPO), str(s.HOME), str(s.SESSIONS), str(v.PREFS)]))"],
        env=env, capture_output=True, text=True, check=True).stdout
    repo, home_, sessions, prefs = json.loads(out)
    assert Path(repo) == code and Path(home_) == home
    assert Path(sessions) == home / "output" / "sessions"
    assert Path(prefs) == home / "output" / ".studio" / "services.json"
