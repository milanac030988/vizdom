@echo off
REM Visual DOM Viewer - Interactive UI Element Inspector
REM Usage:
REM   start_viewer.bat                                          (open empty)
REM   start_viewer.bat --dom result.json                        (load DOM)
REM   start_viewer.bat --dom result.json --screenshot input.png (load both)

cd /d "%~dp0"
call "%~dp0python_env.bat" || exit /b 1
"%VIZDOM_PY%" -m tools.visual_dom_viewer %*
