# Build the paper to PDF with XeLaTeX (same tool resolution as ../report/build.ps1).
#   powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$miktex = Join-Path $env:LOCALAPPDATA "Programs\MiKTeX\miktex\bin\x64"
if (Test-Path (Join-Path $miktex "miktex.exe")) { $env:PATH = "$miktex;$env:PATH" }

function Resolve-Tool([string]$launcher, [string]$engine, [string[]]$engineArgs) {
    if (Get-Command $launcher -ErrorAction SilentlyContinue) { return @($launcher) }
    if (Get-Command $engine -ErrorAction SilentlyContinue) { return @($engine) + $engineArgs }
    throw "neither $launcher nor $engine found - see ../report/build.ps1"
}
$xelatex   = Resolve-Tool "xelatex"   "miktex-xetex"    @("-undump=xelatex")
$bibtex    = Resolve-Tool "bibtex"    "miktex-bibtex"   @()
$xdvipdfmx = Resolve-Tool "xdvipdfmx" "miktex-dvipdfmx" @()

function Run([string[]]$cmd, [string[]]$toolArgs) {
    $exe = $cmd[0]
    $all = @()
    if ($cmd.Count -gt 1) { $all += $cmd[1..($cmd.Count - 1)] }
    $all += $toolArgs
    & $exe @all | Out-Host
    return $LASTEXITCODE
}

Run @("initexmf") @("--set-config-value=[MPM]AutoInstall=1") | Out-Null

$d = "vizdom_paper"
Write-Host "=== Building $d ===" -ForegroundColor Cyan
Run $xelatex @("-no-pdf", "-interaction=nonstopmode", "$d.tex") | Out-Null
Run $bibtex  @($d) | Out-Null
Run $xelatex @("-no-pdf", "-interaction=nonstopmode", "$d.tex") | Out-Null
$rc = Run $xelatex @("-no-pdf", "-interaction=nonstopmode", "$d.tex")
if (-not (Test-Path "$d.xdv") -or $rc -ne 0) {
    Write-Host "[ERROR] ${d}: LaTeX pass failed (exit $rc) - see ${d}.log" -ForegroundColor Red
    exit 1
}
$rc = Run $xdvipdfmx @("-o", "$d.pdf", "$d.xdv")
if ($rc -ne 0) {
    Write-Host "[WARN] could not write $d.pdf (open in a viewer?) - writing ${d}_new.pdf" -ForegroundColor Yellow
    Run $xdvipdfmx @("-o", "${d}_new.pdf", "$d.xdv") | Out-Null
}
Write-Host "-> $d.pdf" -ForegroundColor Green
