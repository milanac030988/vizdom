"""
Detector backend registry.

Central place to construct a detector by name. Backends are lazily instantiated
so importing this module never pulls in torch/ultralytics/OmniParser — those are
only imported when the corresponding backend is actually built.

Usage:
    from visual_dom.adapters.outbound.detectors import create_detector, list_detectors
    backend = create_detector("uied")
    detections = backend.detect(image)
"""

from typing import Any, Callable, Dict, List

from visual_dom.core.ports.outbound.detector_port import Detection, DetectorBackend

# name -> factory(**kwargs) -> DetectorBackend
_FACTORIES: Dict[str, Callable[..., DetectorBackend]] = {}
_META: Dict[str, Dict[str, Any]] = {}


def register(name: str, factory: Callable[..., DetectorBackend], **meta: Any) -> None:
    """Register a backend factory under a name (idempotent)."""
    _FACTORIES[name] = factory
    _META[name] = meta


def _make_uied(**kwargs: Any) -> DetectorBackend:
    from visual_dom.adapters.outbound.detectors.uied_backend import UIEDBackend
    return UIEDBackend(**kwargs)


def _make_yolo(**kwargs: Any) -> DetectorBackend:
    from visual_dom.adapters.outbound.detectors.yolo_backend import YOLOBackend
    return YOLOBackend(**kwargs)


def _make_omniparser(**kwargs: Any) -> DetectorBackend:
    from visual_dom.adapters.outbound.detectors.omniparser_backend import OmniParserBackend
    return OmniParserBackend(**kwargs)


def _make_grpc(**kwargs: Any) -> DetectorBackend:
    from visual_dom.adapters.outbound.detectors.grpc_backend import GrpcDetectorBackend
    return GrpcDetectorBackend(**kwargs)


def _make_modular(**kwargs: Any) -> DetectorBackend:
    from visual_dom.adapters.outbound.detectors.modular_backend import ModularDetectorBackend
    return ModularDetectorBackend(**kwargs)


register("uied", _make_uied, license="project", requires_gpu=False,
         description="Traditional CV coarse-to-fine (default).")
register("yolo", _make_yolo, license="AGPL-3.0", requires_gpu=True,
         description="Ultralytics YOLO; needs a .pt weights file.")
register("omniparser", _make_omniparser, license="AGPL-3.0 (icon_detect)/MIT (icon_caption)",
         requires_gpu=True, description="Microsoft OmniParser; needs repo + weights.")
register("grpc", _make_grpc, license="n/a (remote)", requires_gpu=False,
         description="Remote detector over gRPC (ADR-017); heavy model runs on another host.")
register("modular", _make_modular, license="composite (per stage)", requires_gpu=False,
         description="Three pluggable stages: region proposer + OCR + optional captioner (ADR-027).")


def create_detector(name: str, **kwargs: Any) -> DetectorBackend:
    """
    Construct a detector backend by name.

    Args:
        name: registered backend name ("uied", "yolo", "omniparser")
        **kwargs: forwarded to the backend constructor

    Raises:
        ValueError: if the name is unknown (message lists valid names)
    """
    key = (name or "").lower()
    if key not in _FACTORIES:
        valid = ", ".join(sorted(_FACTORIES))
        raise ValueError(f"Unknown detector backend '{name}'. Available: {valid}")
    return _FACTORIES[key](**kwargs)


def list_detectors() -> List[Dict[str, Any]]:
    """
    Return metadata for all registered backends without constructing them.

    Each entry: {name, description, license, requires_gpu, available}.
    `available` reflects whether the backend's dependencies are importable.
    """
    out: List[Dict[str, Any]] = []
    for name, meta in sorted(_META.items()):
        available = True
        try:
            # is_available lives on the class; import lazily via the factory's module.
            backend_cls = _resolve_class(name)
            available = backend_cls.is_available()
        except Exception:
            available = False
        out.append({
            "name": name,
            "description": meta.get("description", ""),
            "license": meta.get("license", "unknown"),
            "requires_gpu": meta.get("requires_gpu", False),
            "available": available,
        })
    return out


def _resolve_class(name: str):
    """Import and return the backend class for `name` (for is_available checks)."""
    if name == "uied":
        from visual_dom.adapters.outbound.detectors.uied_backend import UIEDBackend
        return UIEDBackend
    if name == "yolo":
        from visual_dom.adapters.outbound.detectors.yolo_backend import YOLOBackend
        return YOLOBackend
    if name == "omniparser":
        from visual_dom.adapters.outbound.detectors.omniparser_backend import OmniParserBackend
        return OmniParserBackend
    if name == "grpc":
        from visual_dom.adapters.outbound.detectors.grpc_backend import GrpcDetectorBackend
        return GrpcDetectorBackend
    raise KeyError(name)
