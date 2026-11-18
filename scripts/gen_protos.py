"""Generate the gRPC stubs in src/visual_dom/generated from protos/*.proto.

The stubs are not tracked; run this once after a checkout and before building the
wheel (the release pipeline does). Needs grpcio-tools (the ``grpc`` extra):

    python scripts/gen_protos.py

protoc writes ``import detector_pb2`` into the *_grpc.py files, which fails inside
a package; the import is qualified to ``from visual_dom.generated import ...``.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOS = ROOT / "protos"
OUT = ROOT / "src" / "visual_dom" / "generated"


def main() -> int:
    try:
        from grpc_tools import protoc
    except ImportError:
        print("grpcio-tools is not installed: pip install \"grpcio-tools>=1.60,<1.63\"", file=sys.stderr)
        return 1
    files = sorted(PROTOS.glob("*.proto"))
    if not files:
        print(f"no .proto files in {PROTOS}", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    args = ["protoc", f"-I{PROTOS}", f"--python_out={OUT}", f"--grpc_python_out={OUT}"]
    args += [str(f) for f in files]
    if protoc.main(args) != 0:
        print("protoc failed", file=sys.stderr)
        return 1
    for grpc_file in OUT.glob("*_pb2_grpc.py"):
        text = grpc_file.read_bytes().decode("utf-8")  # keep protoc's line endings
        fixed = re.sub(r"^import (\w+_pb2) as", r"from visual_dom.generated import \1 as", text, flags=re.M)
        grpc_file.write_bytes(fixed.encode("utf-8"))
    print(f"generated {len(files)} proto(s) into {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
