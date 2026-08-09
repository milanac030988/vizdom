@echo off
REM VizDOM Capture gRPC Service (ADR-018)
REM Runs screenshot capture as a service ON THE HOST/DEVICE UNDER TEST, so the
REM pipeline running elsewhere can pull frames from where the app-under-test is.
REM Point clients at this host with the `grpc` capture strategy and
REM VIZDOM_CAPTURE_TARGET=<this-host>:50053 (or target=<host:port>).
REM
REM Prerequisites (once, in the app's Python 3.9):
REM   "%VIZDOM_PY%" -m pip install grpcio grpcio-tools
REM   generate stubs (see docs/adr/018-pluggable-capture-service.md).
REM
REM Usage:
REM   start_capture.bat                       (OS auto-select strategy, port 50053)
REM   start_capture.bat --strategy windows
REM   start_capture.bat --strategy android --serial <device>
REM   start_capture.bat --strategy camera --kw device=0
REM   start_capture.bat --strategy windows --window-title "Calculator"
REM   start_capture.bat --list                (show discovered strategies)
REM
REM   --window-title <title> is the app this service raises when a client calls
REM   Focus (ADR-021) without naming one. Focus can only happen on the machine
REM   that owns the screen, which is why it is served here.

cd /d "%~dp0"
call "%~dp0python_env.bat" || exit /b 1
set PYTHONPATH=%~dp0src
"%VIZDOM_PY%" -m visual_dom.adapters.inbound.grpc.capture_server %*
