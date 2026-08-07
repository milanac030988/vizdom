"""
VizDOM session configuration (ADR-020).

A single, JSON-serialisable configuration object that a client provides once via
``visual_dom.connect(...)`` (or the Robot Framework ``Connect`` keyword) and that
then drives every stage of a session:

* which **detector** backend and **OCR** engine to use, and their parameters;
* the optional **refiner** (small-LM / VLM) review stage;
* **Stage 2.5 - Merge & Deduplicate** tunables;
* **Stage 3 - Hierarchy Building** tunables;
* size/count **filters**, the **capture** strategy, and **output** options.

The config is a tree of plain dataclasses (no third-party dependency). It has
sensible defaults everywhere, so a partial JSON only needs to override what the
user cares about. Unknown keys are reported (not silently dropped) so typos in a
hand-edited file surface immediately.

Emit an annotated template with all defaults::

    python -m visual_dom.config --init vizdom.config.json

Load it in Python::

    from visual_dom import connect
    session = connect("vizdom.config.json")
    dom = session.analyze("screenshot.png")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, is_dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from visual_dom.logging_utils import get_logger

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Section dataclasses
# --------------------------------------------------------------------------- #

@dataclass
class DetectorConfig:
    """Which detection backend runs, and how (Stage 2 - element detection)."""
    backend: str = "uied"                 # uied | yolo | omniparser | hybrid
    use_gpu: bool = True
    confidence_threshold: float = 0.3     # min detection confidence to keep
    yolo_model_path: Optional[str] = None  # required for backend=yolo/hybrid
    # OmniParser weight paths; null -> auto-resolve from models/omniparser/*.
    omniparser_icon_detect_path: Optional[str] = None
    omniparser_icon_caption_path: Optional[str] = None
    # Feed VizDOM's upscaling OCR into OmniParser to recover missed text (ADR-016).
    omniparser_text_ensemble: bool = True
    # OmniParser YOLO icon-detection confidence cutoff. Default 0.05 (OmniParser's
    # own default). Faint/small glyphs (e.g. a minimize "-" button) can sit just
    # under it and be missed on some captures; lowering to ~0.03 recovers them at a
    # small false-positive cost. Only used when backend == "omniparser".
    omniparser_box_threshold: float = 0.05
    # For backend == "grpc": address of a running detector service (ADR-017),
    # e.g. a GPU host serving one warm OmniParser for many clients.
    grpc_target: str = "localhost:50051"


@dataclass
class OcrConfig:
    """Text-detection engine (Stage 1)."""
    engine: str = "easyocr"               # easyocr | paddleocr | tesseract | none
    languages: List[str] = field(default_factory=lambda: ["en"])
    confidence_threshold: float = 0.3


@dataclass
class RefinerConfig:
    """Optional small-LM / VLM review of detected elements (Stage 8)."""
    enabled: bool = False
    backend: Optional[str] = "ollama"     # ollama | openai
    model: Optional[str] = "qwen2.5:3b"
    host: str = "http://localhost:11434"


@dataclass
class MergeConfig:
    """Stage 2.5 - Merge & Deduplicate tunables."""
    nms_iou_threshold: float = 0.5        # per-type NMS IoU
    cross_type_iou: float = 0.4           # cross-type overlap suppression
    duplicate_tolerance_px: int = 5       # near-identical-box dedup tolerance (px @1080p)
    merge_oversegmented: bool = True      # fuse split multi-line labels/buttons
    group_fill_ratio_min: float = 0.5     # min area-fill for a merge group to apply


@dataclass
class HierarchyConfig:
    """Stage 3 - Hierarchy Building tunables."""
    containment_threshold: float = 0.85   # child-area fraction inside parent
    min_containment_margin: int = 5       # min px margin for parent-child
    use_llm: bool = False                 # LLM hierarchy refinement (needs refiner)
    llm_model: str = "ollama"


@dataclass
class SymbolConfig:
    """Stage 4c - symbol reading on glyph-only elements (template matching)."""
    enabled: bool = True
    # Extra strictness: when set, the winning symbol's template Dice score must
    # also reach this value. Structure decides (ADR-011 v3); this only vetoes.
    min_score: Optional[float] = None


@dataclass
class FilterConfig:
    """Size / count filters (resolution-aware, referenced to 1080p)."""
    min_element_area: int = 100
    min_element_size: int = 10
    max_elements: int = 200


@dataclass
class CaptureConfig:
    """How screens are acquired (ADR-018). Used by the RF client layer."""
    strategy: Optional[str] = None        # null=auto | windows|linux|android|camera|grpc|<plugin>
    target: Optional[str] = None          # host:port when strategy=grpc
    camera_mode: bool = False             # rectify a screen photographed by a camera
    # Application under test, raised by `Bring App To Front` / focus_before_capture
    # (ADR-021). Window title on desktop; package or package/.Activity on Android.
    window_title: Optional[str] = None
    # Raise window_title before every screen grab, so the DOM is always built from
    # the SUT and not from whatever window happens to be on top. Off by default:
    # focusing mutates SUT state, so it is opt-in.
    focus_before_capture: bool = False
    # Capture ONLY window_title's client area instead of the whole screen, giving a
    # DOM with just the SUT's elements. Implies focusing (a crop of an occluded
    # window would show whatever covers it). Falls back to a full-screen grab, with
    # a warning, when the capture strategy cannot scope to a window.
    window_scope: bool = False


@dataclass
class ActuatorConfig:
    """How input is delivered (ADR-019). Used by the RF client layer."""
    strategy: Optional[str] = None   # null=platform default | desktop|android|grpc|<plugin>
    target: Optional[str] = None     # host:port when strategy=grpc
    # Application under test for `Bring App To Front` (ADR-021); defaults to
    # capture.window_title when omitted, since normally both drive the same app.
    window_title: Optional[str] = None


@dataclass
class GroundingConfig:
    """desc= locator resolution (ADR-022): tiered natural-language grounding."""
    # Escalation chain, tried in order. "lexical" is model-free and always safe;
    # "slm" needs the text model below (Ollama/OpenAI); "vlm" additionally needs
    # a vision model and is off by default (least deterministic).
    tiers: List[str] = field(default_factory=lambda: ["lexical", "slm"])
    backend: str = "ollama"               # ollama | openai
    model: str = "qwen2.5:3b"             # text model for the slm tier
    vision_model: str = "qwen2.5-vl:3b"   # vision model for the vlm tier
    host: str = "http://localhost:11434"


@dataclass
class OutputConfig:
    """DOM compilation / output options."""
    generate_locators: bool = True


# --------------------------------------------------------------------------- #
# Root config
# --------------------------------------------------------------------------- #

@dataclass
class VizDomConfig:
    """
    Root VizDOM session configuration.

    Build from a file/dict with :meth:`load`, get an all-defaults instance with
    :meth:`default`, and serialise with :meth:`to_dict` / :meth:`save`.
    """
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    ocr: OcrConfig = field(default_factory=OcrConfig)
    refiner: RefinerConfig = field(default_factory=RefinerConfig)
    merge: MergeConfig = field(default_factory=MergeConfig)
    hierarchy: HierarchyConfig = field(default_factory=HierarchyConfig)
    symbols: SymbolConfig = field(default_factory=SymbolConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    actuator: ActuatorConfig = field(default_factory=ActuatorConfig)
    grounding: GroundingConfig = field(default_factory=GroundingConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    # ---- construction ---------------------------------------------------- #

    @classmethod
    def default(cls) -> "VizDomConfig":
        """A config with every field at its documented default."""
        return cls()

    @classmethod
    def load(cls, source: Union[str, Path, Dict[str, Any], "VizDomConfig", None]) -> "VizDomConfig":
        """
        Build a config from a JSON file path, a dict, an existing config, or None.

        ``None`` yields all defaults. A partial mapping overrides only the keys it
        contains; everything else keeps its default. Unknown keys raise
        ``ValueError`` (a typo should not silently become a no-op).
        """
        if source is None:
            return cls.default()
        if isinstance(source, VizDomConfig):
            return source
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"Config file not found: {path}")
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            log.info("Loaded VizDOM config from %s", path)
        elif isinstance(source, dict):
            data = source
        else:
            raise TypeError(f"Unsupported config source: {type(source).__name__}")
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VizDomConfig":
        """Merge a (possibly partial) mapping onto the defaults, validating keys."""
        if not isinstance(data, dict):
            raise TypeError("Config root must be a JSON object")
        # Ignore metadata/comment keys that start with '_' or '$'.
        data = {k: v for k, v in data.items() if not k.startswith(("_", "$"))}
        section_types = {f.name: f.type for f in fields(cls)}
        unknown = set(data) - set(section_types)
        if unknown:
            raise ValueError(
                f"Unknown config section(s): {sorted(unknown)}. "
                f"Valid sections: {sorted(section_types)}"
            )
        kwargs: Dict[str, Any] = {}
        for name, section_cls in _section_classes(cls).items():
            if name in data:
                kwargs[name] = _build_section(section_cls, name, data[name])
        return cls(**kwargs)

    # ---- serialisation --------------------------------------------------- #

    def to_dict(self) -> Dict[str, Any]:
        """Plain nested dict, suitable for ``json.dump``."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, path: Union[str, Path], indent: int = 2) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.to_json(indent=indent))
        log.info("Wrote VizDOM config to %s", path)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _section_classes(cls) -> Dict[str, type]:
    """Map each root field name to its section dataclass."""
    return {f.name: f.default_factory().__class__ for f in fields(cls)}  # type: ignore[misc]


def _build_section(section_cls: type, name: str, values: Any):
    """Instantiate a section dataclass from a mapping, validating field names."""
    if not isinstance(values, dict):
        raise TypeError(f"Config section '{name}' must be a JSON object")
    values = {k: v for k, v in values.items() if not k.startswith(("_", "$"))}
    valid = {f.name for f in fields(section_cls)}
    unknown = set(values) - valid
    if unknown:
        raise ValueError(
            f"Unknown key(s) in '{name}': {sorted(unknown)}. Valid: {sorted(valid)}"
        )
    return section_cls(**values)


# Human-readable one-line docs per field, emitted as sibling ``_help`` comments in
# the template (JSON has no comments, so we inline guidance the user can delete).
_FIELD_HELP: Dict[str, str] = {
    "detector": "Stage 2 - element detection backend and its parameters",
    "detector.backend": "uied (CPU baseline) | yolo | omniparser (best actionable) | hybrid",
    "detector.confidence_threshold": "0..1; lower = more detections (higher recall)",
    "detector.omniparser_icon_detect_path": "null = auto-resolve from models/omniparser/",
    "detector.omniparser_text_ensemble": "feed VizDOM OCR into OmniParser to recover text (ADR-016)",
    "detector.omniparser_box_threshold": "YOLO icon confidence cutoff (default 0.05); lower to ~0.03 to recover faint glyphs like a minimize button",
    "detector.grpc_target": "host:port of a running detector gRPC service (used only when backend == 'grpc', ADR-017)",
    "ocr": "Stage 1 - text detection engine",
    "ocr.engine": "easyocr | paddleocr | tesseract | none",
    "refiner": "Stage 8 - optional small-LM/VLM element review (needs a running backend)",
    "merge": "Stage 2.5 - Merge & Deduplicate",
    "merge.nms_iou_threshold": "per-type non-max-suppression IoU",
    "merge.cross_type_iou": "suppress overlapping boxes of different types above this IoU",
    "merge.merge_oversegmented": "fuse split multi-line labels/buttons back together",
    "hierarchy": "Stage 3 - Hierarchy Building (containment tree)",
    "hierarchy.containment_threshold": "fraction of a child's area that must sit inside its parent",
    "symbols": "Stage 4c - glyph/operator reading (+ - = x / etc.) via template matching",
    "symbols.min_score": "null = structure decides (default); a value adds a template-agreement veto (raise = stricter)",
    "filter": "resolution-aware size/count filters (referenced to 1080p)",
    "capture": "how screens are acquired (RF client layer, ADR-018)",
    "capture.strategy": "null=auto | windows | linux | android | camera | grpc | <plugin>",
    "capture.window_title": "app under test to raise: window title, or package[/.Activity] on Android (ADR-021)",
    "capture.focus_before_capture": "raise window_title before every grab, so the DOM is built from the app under test and not from whatever window is on top",
    "capture.window_scope": "capture ONLY window_title's client area instead of the whole screen, so the DOM contains just that app (implies focusing; falls back to full screen with a warning if the strategy cannot)",
    "actuator": "how input is delivered (RF client layer, ADR-019)",
    "actuator.strategy": "null=platform default | desktop | android | grpc | <plugin>",
    "actuator.target": "host:port of a running actuator gRPC service (when strategy == grpc)",
    "actuator.window_title": "app to raise for input; null = inherit capture.window_title (ADR-021)",
    "grounding": "desc= locator resolution (ADR-022): tiered natural-language grounding",
    "grounding.tiers": "escalation order; lexical (no model) | slm (text LM over DOM) | vlm (Set-of-Mark over image, opt-in)",
    "output": "DOM compilation options",
}


def annotated_template() -> Dict[str, Any]:
    """
    A full-defaults config as a dict, with a leading ``_help`` block describing
    every section/field. Written by ``--init`` so a user has inline guidance.
    """
    cfg = VizDomConfig.default().to_dict()
    out: Dict[str, Any] = {
        "_about": "VizDOM session config. Provide via connect(<this file>) or the "
                  "Robot Framework 'Connect' keyword. All values below are defaults; "
                  "delete any you don't want to override.",
        "_help": _FIELD_HELP,
    }
    out.update(cfg)
    return out


def write_template(path: Union[str, Path]) -> Path:
    """Write the annotated default template to ``path`` and return it."""
    path = Path(path)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(annotated_template(), fh, indent=2, ensure_ascii=False)
    return path


# --------------------------------------------------------------------------- #
# CLI: python -m visual_dom.config --init [path]
# --------------------------------------------------------------------------- #

def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="python -m visual_dom.config",
        description="Emit or validate a VizDOM session config.",
    )
    parser.add_argument("--init", metavar="PATH", nargs="?", const="vizdom.config.json",
                        help="write an annotated default template (default path: "
                             "vizdom.config.json)")
    parser.add_argument("--check", metavar="PATH",
                        help="validate an existing config file and print the resolved config")
    args = parser.parse_args(argv)

    if args.init is not None:
        out = write_template(args.init)
        print(f"Wrote annotated template to {out}")
        return 0
    if args.check:
        try:
            cfg = VizDomConfig.load(args.check)
        except Exception as exc:  # noqa: BLE001
            print(f"INVALID: {exc}", file=sys.stderr)
            return 1
        print("OK - config is valid.")
        print(cfg.to_json())
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
