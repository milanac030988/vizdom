"""
Detector service CLI -> backend kwargs, for the ADR-027 modular backend.

The service used to publish resolved OmniParser paths into os.environ (leaking
into every later run and child process), dropped --box-threshold for modular
and replaced an explicit "no OCR" with easyocr. `serve` is stubbed: these tests
only check what main() would build the backend with.
"""

import os
import sys

import pytest

from visual_dom.adapters.inbound.grpc import detector_server
from visual_dom.adapters.outbound.detectors import omniparser_paths

ENV_VARS = ("OMNIPARSER_ROOT", "OMNIPARSER_ICON_DETECT", "OMNIPARSER_ICON_CAPTION")


@pytest.fixture
def run_main(monkeypatch, tmp_path):
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(omniparser_paths, "_PROJECT_ROOT", str(tmp_path / "empty"))
    captured = {}
    monkeypatch.setattr(detector_server, "serve",
                        lambda backend, port, kwargs: captured.update(
                            backend=backend, kwargs=kwargs))

    def run(*argv):
        monkeypatch.setattr(sys, "argv", ["detector_server", *argv])
        detector_server.main()
        return captured["kwargs"]

    return run


def test_modular_forwards_paths_and_box_threshold_without_touching_env(run_main):
    kwargs = run_main("--backend", "modular", "--icon-detect", "/w/model.pt",
                      "--omniparser-root", "/repo", "--box-threshold", "0.03")
    assert kwargs["icon_detect_path"] == "/w/model.pt"
    assert kwargs["omniparser_root"] == "/repo"
    assert kwargs["box_threshold"] == 0.03
    assert kwargs["region_proposer"] == "auto"
    assert not any(os.environ.get(v) for v in ENV_VARS)


def test_modular_ocr_none_is_kept(run_main):
    assert run_main("--backend", "modular", "--ocr", "none")["ocr_engine"] == "none"


def test_omitted_ocr_takes_the_per_backend_default(run_main):
    assert run_main("--backend", "modular")["ocr_engine"] == "easyocr"
    assert "ocr_provider" not in run_main("--backend", "omniparser")


def test_modular_explicit_omniparser_needs_weights(run_main):
    with pytest.raises(SystemExit):
        run_main("--backend", "modular", "--regions", "omniparser")


def test_stage_flags_warn_for_other_backends(run_main, caplog):
    run_main("--backend", "uied", "--captioner", "florence")
    assert "--captioner applies to --backend modular only" in caplog.text
