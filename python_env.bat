@echo off
REM ---------------------------------------------------------------------------
REM Resolve ONE Python interpreter for every VizDOM launcher.
REM
REM Called by start_detector / start_capture / start_actuator / start_viewer /
REM start_dashboard / run_demo, which previously each hardcoded an absolute path
REM (D:\Python\python39\python.exe) - so the repository only ran on one machine.
REM
REM Resolution order (first hit wins), documented in docs/uv-setup.md:
REM   1. %VIZDOM_PYTHON%              explicit override - always wins
REM   2. .venv\Scripts\python.exe     an in-project environment (uv venv / venv)
REM   3. D:\Python\python39\...       this workstation's CUDA-enabled 3.9
REM   4. py -3.9                      the Windows launcher, if 3.9 is registered
REM   5. python on PATH               last resort
REM
REM Sets VIZDOM_PY (quoted-safe, no surrounding quotes) and exits 1 with an
REM actionable message when nothing is usable.
REM ---------------------------------------------------------------------------

set "VIZDOM_PY="

REM 1. explicit override
if defined VIZDOM_PYTHON (
    if exist "%VIZDOM_PYTHON%" (
        set "VIZDOM_PY=%VIZDOM_PYTHON%"
        goto :found
    )
    echo [python_env] VIZDOM_PYTHON is set but not found: %VIZDOM_PYTHON%
    exit /b 1
)

REM 2. in-project environment (what `uv venv` / `python -m venv .venv` creates)
if exist "%~dp0.venv\Scripts\python.exe" (
    set "VIZDOM_PY=%~dp0.venv\Scripts\python.exe"
    goto :found
)

REM 3. this workstation's Python 3.9 (has torch 2.4.1+cu124)
if exist "D:\Python\python39\python.exe" (
    set "VIZDOM_PY=D:\Python\python39\python.exe"
    goto :found
)

REM 4. the Windows launcher, asking for 3.9 specifically
py -3.9 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%P in ('py -3.9 -c "import sys;print(sys.executable)"') do set "VIZDOM_PY=%%P"
    if defined VIZDOM_PY goto :found
)

REM 5. whatever `python` means here
python -c "import sys" >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)"') do set "VIZDOM_PY=%%P"
    if defined VIZDOM_PY goto :found
)

echo [python_env] No usable Python found.
echo               Create an environment:   uv venv --python 3.9  ^&^&  uv pip install -e ".[ocr,grpc]"
echo               or point at one:         set VIZDOM_PYTHON=C:\path\to\python.exe
echo               See docs/uv-setup.md
exit /b 1

:found
exit /b 0
