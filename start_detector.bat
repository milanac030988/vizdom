@echo off
REM VizDOM Detector gRPC Service (ADR-017)
REM Runs the heavy detector (OmniParser / YOLO / UIED) as a service so remote
REM clients (CLI / Viewer, on this or other PCs) share ONE warm model instead of
REM each loading it. Point clients at this host with --detector grpc
REM --detector-target <this-host>:50051 (CLI) or the Viewer's grpc target field.
REM
REM Prerequisites (once, in the app's Python 3.9):
REM   "D:\Python\python39\python.exe" -m pip install grpcio grpcio-tools
REM   generate stubs (see docs/adr/017-distributed-hexagonal-grpc.md).
REM
REM Usage:
REM   start_detector.bat                                      (uied, port 50051 - quick test)
REM   start_detector.bat --backend omniparser --port 50051 ^
REM       --icon-detect models\omniparser\icon_detect\model.pt ^
REM       --icon-caption models\omniparser\icon_caption_florence
REM   start_detector.bat --backend yolo --yolo-model models\pretrained\best.pt
REM   (omniparser also auto-detects models\omniparser\ + third_party\OmniParser)

cd /d "%~dp0"
set PYTHONPATH=%~dp0src
if "%~1"=="" (
    REM no args -> lightweight uied service for a quick connectivity test
    "D:\Python\python39\python.exe" -m visual_dom.rpc.detector_server --backend uied --port 50051
) else (
    "D:\Python\python39\python.exe" -m visual_dom.rpc.detector_server %*
)
