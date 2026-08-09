@echo off
REM VizDOM Windows Calculator demo (examples\windows_calculator_demo\README.md)
REM
REM Runs the demo with the PROJECT'S Python, the same interpreter the services
REM use. Do not launch the .robot file directly: Windows then runs whatever
REM Python owns the .robot file association - typically one without easyocr -
REM and the session fails fast with "OCR engine 'easyocr' is not installed".
REM
REM Prerequisite: the three services are running (start_detector.bat,
REM start_capture.bat, start_actuator.bat). Results land in output\demo_run.
REM
REM Usage:
REM   run_demo.bat                                  (both tests)
REM   run_demo.bat --test "Calculator Adds*"        (any robot option is forwarded)

cd /d "%~dp0"
call "%~dp0python_env.bat" || exit /b 1
set PYTHONPATH=%~dp0src
"%VIZDOM_PY%" -m robot --outputdir output\demo_run %* examples\windows_calculator_demo\calculator_demo.robot
