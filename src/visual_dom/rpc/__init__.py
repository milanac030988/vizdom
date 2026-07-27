"""
gRPC transport for VizDOM model services (ADR-017 detector, ADR-018 capture).

Generated stubs (<name>_pb2.py, <name>_pb2_grpc.py) are produced from the .proto
files in protos/ — they are NOT committed; build them with:

    pip install grpcio grpcio-tools
    python -m grpc_tools.protoc -I protos \\
      --python_out=src/visual_dom/rpc --grpc_python_out=src/visual_dom/rpc \\
      protos/detector.proto protos/capture.proto

Then fix each generated grpc stub's import (protoc emits an absolute import that
breaks inside a package):
    detector_pb2_grpc.py:  import detector_pb2  ->  from . import detector_pb2
    capture_pb2_grpc.py:   import capture_pb2   ->  from . import capture_pb2
(e.g. `sed -i 's/^import \\(.*\\)_pb2/from . import \\1_pb2/' \\
  src/visual_dom/rpc/*_pb2_grpc.py`)
"""
