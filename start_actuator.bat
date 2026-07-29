@echo off
REM VizDOM Actuator gRPC Service (ADR-019)
REM Runs input actuation as a service ON THE HOST/DEVICE UNDER TEST (or a robot
REM arm's controller), so the pipeline/orchestration running elsewhere can drive
REM input where the app-under-test is. Point clients at this host with the `grpc`
REM actuator strategy and VIZDOM_ACTUATOR_TARGET=<this-host>:50054 (or target=host:port).
REM
REM Prerequisites (once, in the app's Python 3.9):
REM   "D:\Python\python39\python.exe" -m pip install grpcio grpcio-tools
REM   generate stubs (see docs/adr/019-pluggable-actuator-service.md).
REM
REM Usage:
REM   start_actuator.bat                        (OS auto-select strategy, port 50054)
REM   start_actuator.bat --strategy desktop
REM   start_actuator.bat --strategy android --serial <device>
REM   start_actuator.bat --strategy robot-arm --kw port=COM3
REM   start_actuator.bat --list                 (show discovered strategies)

cd /d "%~dp0"
set PYTHONPATH=%~dp0src
"D:\Python\python39\python.exe" -m visual_dom.rpc.actuator_server %*
