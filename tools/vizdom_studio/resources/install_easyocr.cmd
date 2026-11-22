@echo off
rem Adds EasyOCR (CPU PyTorch and the English models) to the Python of an
rem online VizDOM Studio install. The installer runs it when EasyOCR is ticked;
rem run it again by hand to add EasyOCR later. The versions are the ones the
rem full (offline) installer of the same release ships.
setlocal
set "HERE=%~dp0"
set "PY=%HERE%..\python\python.exe"
if not exist "%PY%" (
  echo Studio's Python is missing: %PY%
  exit /b 3
)

echo Downloading EasyOCR and CPU PyTorch...
"%PY%" -m pip install --disable-pip-version-check --no-warn-script-location --progress-bar off ^
  --extra-index-url https://download.pytorch.org/whl/cpu ^
  -c "%HERE%constraints.txt" -r "%HERE%easyocr-requirements.txt"
if errorlevel 1 exit /b 1

echo Downloading the EasyOCR English models...
set "EASYOCR_MODULE_PATH=%HERE%..\easyocr"
"%PY%" -c "import easyocr; easyocr.Reader(['en'], gpu=False, verbose=False); print('EasyOCR is ready')"
if errorlevel 1 exit /b 2
exit /b 0
