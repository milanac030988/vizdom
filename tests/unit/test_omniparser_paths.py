"""
OmniParser path resolution and the modular detector's 'auto' stage 1.

Before, the "weights found, else uied" fallback lived in each caller (Viewer,
detector service) and the config-file path had none: `detector.backend:
modular` on a machine without the weights built an omniparser proposer, which
raised, and the pipeline silently produced OCR-only DOMs. These tests pin the
fallback in the component, the shared resolution order, and that nothing is
written to os.environ.
"""

import os
import sys

import numpy as np
import pytest

from visual_dom.adapters.outbound.detectors import modular_backend, omniparser_paths
from visual_dom.adapters.outbound.detectors.modular_backend import (
    ModularDetectorBackend, NoneCaptioner, UIEDRegionProposer, create_captioner,
    create_region_proposer,
)
from visual_dom.adapters.outbound.detectors.omniparser_paths import (
    box_threshold_from_env, omniparser_unavailable_reason, resolve_omniparser_paths,
)
from visual_dom.core.ports.outbound.region_proposer_port import RegionProposer

ENV_VARS = ("OMNIPARSER_ROOT", "OMNIPARSER_ICON_DETECT", "OMNIPARSER_ICON_CAPTION",
            "OMNIPARSER_BOX_THRESHOLD")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    # No standard-location weights either, whatever the checkout holds.
    monkeypatch.setattr(omniparser_paths, "_PROJECT_ROOT", str(tmp_path / "empty"))


def make_standard_layout(root):
    weights = root / "models" / "omniparser" / "icon_detect"
    weights.mkdir(parents=True)
    (weights / "model.pt").write_bytes(b"")
    (root / "models" / "omniparser" / "icon_caption_florence").mkdir()
    (root / "third_party" / "OmniParser").mkdir(parents=True)


class FakeText:
    ocr_engine = "fake"

    def detect(self, image, **kwargs):
        return []


# --------------------------------------------------------------------------
# resolve_omniparser_paths
# --------------------------------------------------------------------------

def test_nothing_found_resolves_nothing():
    assert resolve_omniparser_paths() == {}


def test_standard_locations_are_found(tmp_path):
    make_standard_layout(tmp_path)
    paths = resolve_omniparser_paths(project_root=str(tmp_path))
    assert paths["icon_detect_path"].endswith(os.path.join("icon_detect", "model.pt"))
    assert paths["icon_caption_path"].endswith("icon_caption_florence")
    assert paths["omniparser_root"].endswith(os.path.join("third_party", "OmniParser"))


def test_explicit_beats_env_beats_standard(tmp_path, monkeypatch):
    make_standard_layout(tmp_path)
    monkeypatch.setenv("OMNIPARSER_ICON_DETECT", "/env/model.pt")
    monkeypatch.setenv("OMNIPARSER_ROOT", "/env/root")
    paths = resolve_omniparser_paths(omniparser_root="/explicit/root",
                                     project_root=str(tmp_path))
    assert paths["omniparser_root"] == "/explicit/root"
    assert paths["icon_detect_path"] == "/env/model.pt"
    assert paths["icon_caption_path"].endswith("icon_caption_florence")


def test_resolution_never_writes_the_environment(tmp_path):
    make_standard_layout(tmp_path)
    before = {v: os.environ.get(v) for v in ENV_VARS}
    resolve_omniparser_paths(project_root=str(tmp_path))
    assert {v: os.environ.get(v) for v in ENV_VARS} == before


def test_box_threshold_from_env(monkeypatch):
    assert box_threshold_from_env() is None
    monkeypatch.setenv("OMNIPARSER_BOX_THRESHOLD", "0.03")
    assert box_threshold_from_env() == pytest.approx(0.03)
    monkeypatch.setenv("OMNIPARSER_BOX_THRESHOLD", "faint")
    assert box_threshold_from_env(0.05) == 0.05


# --------------------------------------------------------------------------
# omniparser_unavailable_reason: weights alone are not enough
# --------------------------------------------------------------------------

def test_missing_weights_is_a_reason():
    reason = omniparser_unavailable_reason(None, {"icon_detect weights": None})
    assert "icon_detect weights" in reason


def test_weights_without_repo_is_a_reason(tmp_path, monkeypatch):
    weights = tmp_path / "model.pt"
    weights.write_bytes(b"")
    monkeypatch.setattr(omniparser_paths, "_module_missing", lambda name: False)
    modules_before = set(sys.modules)
    reason = omniparser_unavailable_reason(str(tmp_path / "no-repo"),
                                           {"icon_detect weights": str(weights)})
    assert "OMNIPARSER_ROOT" in reason
    # Probed on disk: no stray top-level `util` gets imported and cached.
    assert "util" not in set(sys.modules) - modules_before


def test_repo_found_on_disk_under_its_root(tmp_path, monkeypatch):
    weights = tmp_path / "model.pt"
    weights.write_bytes(b"")
    (tmp_path / "repo" / "util").mkdir(parents=True)
    (tmp_path / "repo" / "util" / "utils.py").write_text("")
    monkeypatch.setattr(omniparser_paths, "_module_missing", lambda name: False)
    assert omniparser_unavailable_reason(str(tmp_path / "repo"),
                                         {"icon_detect weights": str(weights)}) is None


def test_weights_without_ultralytics_is_a_reason(tmp_path, monkeypatch):
    weights = tmp_path / "model.pt"
    weights.write_bytes(b"")
    monkeypatch.setattr(omniparser_paths, "_module_missing",
                        lambda name: name == "ultralytics")
    reason = omniparser_unavailable_reason(None, {"icon_detect weights": str(weights)})
    assert "ultralytics" in reason


# --------------------------------------------------------------------------
# region proposer 'auto' and the backend default
# --------------------------------------------------------------------------

def test_auto_degrades_to_uied_without_weights(caplog):
    proposer = create_region_proposer("auto")
    assert isinstance(proposer, UIEDRegionProposer)
    assert "uied region proposer" in caplog.text


def test_auto_degrades_to_uied_when_omniparser_fails_to_load(monkeypatch, caplog):
    monkeypatch.setattr(omniparser_paths, "omniparser_unavailable_reason",
                        lambda root, required=None: None)

    def boom(**kwargs):
        raise ImportError("No module named 'util'")

    monkeypatch.setattr(modular_backend, "OmniParserRegionProposer", boom)
    proposer = create_region_proposer("auto", icon_detect_path="/w/model.pt")
    assert isinstance(proposer, UIEDRegionProposer)
    assert "loading it failed" in caplog.text


def test_auto_picks_omniparser_with_resolved_paths(monkeypatch):
    monkeypatch.setattr(omniparser_paths, "omniparser_unavailable_reason",
                        lambda root, required=None: None)
    seen = {}

    class FakeOmni(RegionProposer):
        name = "omniparser"

        def __init__(self, **kwargs):
            seen.update(kwargs)

        def propose(self, image):
            return []

    monkeypatch.setattr(modular_backend, "OmniParserRegionProposer", FakeOmni)
    proposer = create_region_proposer("auto", icon_detect_path="/w/model.pt",
                                      box_threshold=0.03)
    assert isinstance(proposer, FakeOmni)
    assert seen["icon_detect_path"] == "/w/model.pt"
    assert seen["box_threshold"] == 0.03


def test_backend_default_degrades_the_stage_not_the_backend():
    """The config-file path: `detector.backend: modular` with no weights."""
    backend = ModularDetectorBackend(text_detector=FakeText())
    assert backend._proposer.name == "uied"
    backend.detect(np.full((200, 300, 3), 255, dtype=np.uint8))


# --------------------------------------------------------------------------
# captioner 'auto' (the Viewer's default since 2026-10-31)
# --------------------------------------------------------------------------

def test_captioner_auto_degrades_to_none_without_weights(caplog):
    captioner = create_captioner("auto")
    assert isinstance(captioner, NoneCaptioner)
    assert "florence captioner unavailable" in caplog.text


def test_captioner_auto_degrades_with_weights_but_no_repo(tmp_path, monkeypatch, caplog):
    """The review's case: caption weights resolve, util.utils does not."""
    weights = tmp_path / "icon_caption_florence"
    weights.mkdir()
    monkeypatch.setattr(omniparser_paths, "_module_missing", lambda name: False)
    captioner = create_captioner("auto", icon_caption_path=str(weights),
                                 omniparser_root=str(tmp_path / "no-repo"))
    assert isinstance(captioner, NoneCaptioner)
    assert "OMNIPARSER_ROOT" in caplog.text


def test_captioner_auto_degrades_when_florence_fails_to_load(monkeypatch, caplog):
    monkeypatch.setattr(omniparser_paths, "omniparser_unavailable_reason",
                        lambda root, required=None: None)

    def boom(**kwargs):
        raise AttributeError("'Florence2ForConditionalGeneration' object has "
                             "no attribute '_supports_sdpa'")

    monkeypatch.setattr(modular_backend, "FlorenceCaptioner", boom)
    captioner = create_captioner("auto", icon_caption_path="/w/florence")
    assert isinstance(captioner, NoneCaptioner)
    assert "loading it failed" in caplog.text


def test_captioner_auto_picks_florence_with_resolved_paths(monkeypatch):
    monkeypatch.setattr(omniparser_paths, "omniparser_unavailable_reason",
                        lambda root, required=None: None)
    seen = {}

    class FakeFlorence(NoneCaptioner):
        name = "florence"

        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(modular_backend, "FlorenceCaptioner", FakeFlorence)
    captioner = create_captioner("auto", icon_caption_path="/w/florence")
    assert isinstance(captioner, FakeFlorence)
    assert seen["icon_caption_path"] == "/w/florence"


def test_explicit_florence_still_fails_fast():
    with pytest.raises(ValueError, match="icon_caption"):
        create_captioner("florence")


def test_backend_with_captioner_auto_keeps_detecting():
    """The Viewer path: modular + auto on a machine Florence cannot run on."""
    backend = ModularDetectorBackend(text_detector=FakeText(), captioner="auto")
    assert backend._captioner.name == "none"
    backend.detect(np.full((200, 300, 3), 255, dtype=np.uint8))


def test_backend_forwards_paths_and_box_threshold_to_the_stages(monkeypatch):
    calls = {}
    monkeypatch.setattr(modular_backend, "create_region_proposer",
                        lambda name, **kw: calls.setdefault("regions", kw)
                        and UIEDRegionProposer())
    monkeypatch.setattr(modular_backend, "create_captioner",
                        lambda name, **kw: calls.setdefault("captioner", kw)
                        and modular_backend.NoneCaptioner())
    ModularDetectorBackend(text_detector=FakeText(), omniparser_root="/r",
                           icon_detect_path="/d.pt", icon_caption_path="/c",
                           box_threshold=0.03,
                           region_kwargs={"box_threshold": 0.04})
    assert calls["regions"] == {"omniparser_root": "/r", "icon_detect_path": "/d.pt",
                                "box_threshold": 0.04}    # explicit stage kwarg wins
    assert calls["captioner"] == {"omniparser_root": "/r", "icon_caption_path": "/c"}


def test_pipeline_modular_without_weights_still_builds_a_backend():
    """The silent-degradation bug: this used to return None (OCR-only DOMs)."""
    from visual_dom.core.domain.pipeline import VisualDOMPipeline

    pipeline = VisualDOMPipeline(ocr_engine="none", use_gpu=False, detector="modular")
    assert pipeline._primary_backend is not None
    assert pipeline._primary_backend._proposer.name == "uied"


def test_config_file_modular_builds_a_backend_and_forwards_paths(monkeypatch):
    """`detector.backend: modular` in a session config: no weights -> uied
    stage, and the omniparser_* config fields reach the modular stages."""
    from visual_dom.config import VizDomConfig
    from visual_dom.context import Session

    seen = {}
    real = modular_backend.create_region_proposer
    monkeypatch.setattr(modular_backend, "create_region_proposer",
                        lambda name, **kw: seen.update(kw) or real(name, **kw))
    cfg = VizDomConfig.from_dict({
        "detector": {"backend": "modular", "use_gpu": False,
                     "omniparser_box_threshold": 0.03},
        "ocr": {"engine": "none"},
    })
    pipeline = Session._build_pipeline(cfg)
    assert pipeline._primary_backend._proposer.name == "uied"
    assert seen["box_threshold"] == 0.03


def test_default_captioner_accepts_forwarded_paths(tmp_path):
    """Regression: with OmniParser paths known, `captioner="none"` (the
    default) raised TypeError, crashing `--backend modular` at startup and
    silently degrading the config path to OCR-only DOMs."""
    from visual_dom.adapters.outbound.detectors import create_detector

    make_standard_layout(tmp_path)
    paths = resolve_omniparser_paths(project_root=str(tmp_path))
    backend = create_detector("modular", captioner="none", region_proposer="uied",
                              text_detector=FakeText(), **paths)
    assert backend._captioner.name == "none"
