<#
.SYNOPSIS
  Assemble everything the all-in-one VizDOM Studio installer ships beside the
  Electron app, into tools/vizdom_studio/bundle/ (electron-builder's extraResources):

    bundle/python/     relocatable CPython (uv-managed, python-build-standalone) with
                       VizDOM + the Robot Framework library ([robot,studio] extras)
                       and CPU-only torch for EasyOCR
    bundle/vizdom/     tools/vizdom_bridge, tools/visual_dom_viewer, plugins/, example config
    bundle/easyocr/    EasyOCR's English models, fetched once so Studio works offline
    bundle/tesseract/  a copy of an installed Tesseract-OCR folder (optional)
    bundle/wheels/     the VizDOM wheel itself, which the installer can pip-install
                       into a Python the user already has (resources/installer.nsh)

  -Lite assembles the online installer instead: no PyTorch, no EasyOCR and no
  models (Tesseract reads the text), plus

    bundle/online/     install_easyocr.cmd, which the installer runs when EasyOCR is
                       ticked, with the exact versions to download (constraints.txt,
                       easyocr-requirements.txt) taken from a full bundle

  so both installers of a release carry the same package versions. Build the full
  bundle first with -FreezeOut, then the lite one with -Constraints set to that file.

.EXAMPLE
  # after: python scripts/gen_protos.py ; uv build --wheel
  powershell -File tools/vizdom_studio/scripts/bundle_python.ps1 -Wheel dist\vizdom-0.1.0-py3-none-any.whl -FreezeOut versions.txt
  # ... npm run dist, then the online installer:
  powershell -File tools/vizdom_studio/scripts/bundle_python.ps1 -Wheel dist\vizdom-0.1.0-py3-none-any.whl -Lite -Constraints versions.txt

  Needs uv on PATH (https://docs.astral.sh/uv/) and internet access (PyPI, the
  PyTorch CPU index, EasyOCR's model download).
#>
param(
  [Parameter(Mandatory = $true)][string]$Wheel,
  [string]$PythonVersion = "3.12",
  [string]$TesseractDir = "C:\Program Files\Tesseract-OCR",
  [switch]$SkipEasyOcrModels,
  [switch]$Lite,
  [string]$Constraints,
  [string]$FreezeOut
)

$ErrorActionPreference = "Stop"
$studio = Split-Path -Parent $PSScriptRoot
$repo = Resolve-Path (Join-Path $studio "..\..")
$bundle = Join-Path $studio "bundle"
$Wheel = (Resolve-Path $Wheel).Path

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Run($exe, [string[]]$argv) {
  & $exe @argv
  if ($LASTEXITCODE -ne 0) { throw "$exe $($argv -join ' ') failed with exit code $LASTEXITCODE" }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv is not on PATH: https://docs.astral.sh/uv/" }
if ($Lite) {
  if (-not $Constraints) { throw "-Lite needs -Constraints: the version list a full bundle wrote with -FreezeOut" }
  $Constraints = (Resolve-Path $Constraints).Path
}
if ($FreezeOut) { $FreezeOut = [IO.Path]::GetFullPath($FreezeOut) }

Step "Clean $bundle"
if (Test-Path $bundle) { Remove-Item $bundle -Recurse -Force }
New-Item -ItemType Directory -Force $bundle | Out-Null

# --- 1. a relocatable interpreter ------------------------------------------------
Step "Python $PythonVersion (uv-managed, relocatable)"
$pyhome = Join-Path $bundle "_pyhome"
$env:UV_PYTHON_INSTALL_DIR = $pyhome
# --no-bin: no python3.x.exe shim in ~/.local/bin, the build machine stays untouched
Run uv @("python", "install", "--no-bin", $PythonVersion)
# uv also creates a minor-version link (cpython-3.12-...) beside the real folder
# (cpython-3.12.16-...); take the real one, never the link
$installed = Get-ChildItem $pyhome -Directory |
  Where-Object { $_.Name -like "cpython-*" -and -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -and
                 (Test-Path (Join-Path $_.FullName "python.exe")) } |
  Select-Object -First 1
if (-not $installed) { throw "uv did not install a CPython under $pyhome" }
Write-Host "    using $($installed.Name)"
Copy-Item $installed.FullName (Join-Path $bundle "python") -Recurse
Remove-Item $pyhome -Recurse -Force
Remove-Item Env:\UV_PYTHON_INSTALL_DIR
$py = Join-Path $bundle "python\python.exe"
# uv marks its interpreters externally managed; this one is ours to fill
Get-ChildItem (Join-Path $bundle "python") -Recurse -Filter "EXTERNALLY-MANAGED" | Remove-Item -Force
Run $py @("--version")

# --- 2. packages -----------------------------------------------------------------
$wheelUri = ([Uri]$Wheel).AbsoluteUri
if ($Lite) {
  # everything of [robot,studio] except EasyOCR and the PyTorch it runs on
  Step "VizDOM + Robot Framework library without EasyOCR, versions from $([IO.Path]::GetFileName($Constraints))"
  Run uv @("pip", "install", "--python", $py, "--break-system-packages", "-c", $Constraints,
           "vizdom[desktop,grpc,studio] @ $wheelUri", "pytesseract")

  Step "EasyOCR download for the installer (resources/online)"
  $online = Join-Path $bundle "online"
  New-Item -ItemType Directory -Force $online | Out-Null
  Copy-Item $Constraints (Join-Path $online "constraints.txt")
  $req = @(Get-Content $Constraints | Where-Object { $_ -match '^(easyocr|torch|torchvision)==' })
  if ($req.Count -ne 3) { throw "$Constraints should pin easyocr, torch and torchvision; found: $($req -join ', ')" }
  Set-Content -Encoding ascii (Join-Path $online "easyocr-requirements.txt") $req
  Copy-Item (Join-Path $studio "resources\install_easyocr.cmd") $online
  Write-Host "    $($req -join ', ')"
} else {
  Step "CPU-only torch (EasyOCR's engine)"
  Run uv @("pip", "install", "--python", $py, "--break-system-packages",
           "--index-url", "https://download.pytorch.org/whl/cpu", "torch", "torchvision")

  Step "VizDOM + Robot Framework library from $([IO.Path]::GetFileName($Wheel))"
  Run uv @("pip", "install", "--python", $py, "--break-system-packages",
           "vizdom[robot,studio] @ $wheelUri")

  if ($FreezeOut) {
    # the exact versions, for the online installer's download (-Lite -Constraints)
    Step "Package versions -> $FreezeOut"
    $frozen = @(& uv pip freeze --python $py | Where-Object { $_ -and $_ -notmatch '^vizdom[ =@]' })
    if ($LASTEXITCODE -ne 0) { throw "uv pip freeze failed" }
    Set-Content -Encoding ascii $FreezeOut $frozen
  }
}

# The same wheel, for the installer page that adds the Robot Framework library to
# a Python of the user's own (resources/installer.nsh)
Step "Wheel for the user's own Python"
$wheels = Join-Path $bundle "wheels"
New-Item -ItemType Directory -Force $wheels | Out-Null
Copy-Item $Wheel $wheels

# --- 3. the code Studio runs that is not in the wheel ----------------------------
Step "Bridge, Viewer exporters, plugins"
$code = Join-Path $bundle "vizdom"
foreach ($dir in @("tools\vizdom_bridge", "tools\visual_dom_viewer", "plugins")) {
  $src = Join-Path $repo $dir
  if (Test-Path $src) {
    Copy-Item $src (Join-Path $code $dir) -Recurse
  }
}
Copy-Item (Join-Path $repo "vizdom.config.example.json") $code
Get-ChildItem $code -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

# --- 4. OCR models and engine ----------------------------------------------------
$easy = Join-Path $bundle "easyocr"
New-Item -ItemType Directory -Force $easy | Out-Null
if (-not $SkipEasyOcrModels -and -not $Lite) {
  Step "EasyOCR English models"
  $env:EASYOCR_MODULE_PATH = $easy
  Run $py @("-c", "import easyocr; easyocr.Reader(['en'], gpu=False, verbose=False); print('easyocr models ready')")
  Remove-Item Env:\EASYOCR_MODULE_PATH
}

$tess = Join-Path $bundle "tesseract"
if (Test-Path (Join-Path $TesseractDir "tesseract.exe")) {
  Step "Tesseract from $TesseractDir"
  Copy-Item $TesseractDir $tess -Recurse
} else {
  Write-Warning "No tesseract.exe under ${TesseractDir} - the installer ships without Tesseract (EasyOCR still works)."
  New-Item -ItemType Directory -Force $tess | Out-Null
}

# --- 5. leave out what only building software needs -------------------------------
Step "Remove build-only files (C++ headers, link libraries, test suites)"
$site = Join-Path $bundle "python\Lib\site-packages"
$torchDir = Join-Path $site "torch"
if (Test-Path $torchDir) {
  Remove-Item (Join-Path $torchDir "include") -Recurse -Force -ErrorAction SilentlyContinue
  Get-ChildItem (Join-Path $torchDir "lib") -Filter "*.lib" | Remove-Item -Force
}
Get-ChildItem $site -Recurse -Directory -Filter "tests" | Sort-Object { $_.FullName.Length } |
  ForEach-Object { if (Test-Path $_.FullName) { Remove-Item $_.FullName -Recurse -Force } }

# --- 6. smoke test: the bundle imports what Studio and a Robot suite need -------
Step "Smoke test"
$env:PYTHONPATH = Join-Path $code "tools"
$env:VIZDOM_REPO = $code
$env:VIZDOM_HOME = Join-Path $bundle "_home"
$imports = "import VisualGuiLibrary, visual_dom, visual_gui_library, vizdom_bridge.server, mss, pyautogui, grpc, robot, pytesseract, cv2"
# the online installer downloads EasyOCR with the bundle's own pip
if ($Lite) { $imports += ", pip" } else { $imports += ", easyocr" }
Run $py @("-c", "$imports; from visual_dom.generated import detector_pb2_grpc; assert cv2.__version__.startswith('4.'), cv2.__version__; print('imports ok, Robot Framework', robot.__version__, 'OpenCV', cv2.__version__)")
if (-not $Lite -and -not $SkipEasyOcrModels) {
  # the models load from the bundle, with the build-only files gone
  $env:EASYOCR_MODULE_PATH = $easy
  Run $py @("-c", "import easyocr; easyocr.Reader(['en'], gpu=False, verbose=False, download_enabled=False); print('easyocr loads offline')")
  Remove-Item Env:\EASYOCR_MODULE_PATH
}
Remove-Item Env:\PYTHONPATH, Env:\VIZDOM_REPO, Env:\VIZDOM_HOME
if (Test-Path (Join-Path $bundle "_home")) { Remove-Item (Join-Path $bundle "_home") -Recurse -Force }

$size = (Get-ChildItem $bundle -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Step ("Bundle ready: {0:N0} MB in {1}" -f $size, $bundle)
