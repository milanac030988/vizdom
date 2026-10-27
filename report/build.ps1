# Build the VizDOM reports to PDF with XeLaTeX.
#   powershell -ExecutionPolicy Bypass -File build.ps1                    # builds all four
#   powershell -ExecutionPolicy Bypass -File build.ps1 vizdom_report_en   # builds one
#
# Same tool resolution as build.bat: MiKTeX's xelatex.exe / bibtex.exe /
# xdvipdfmx.exe launchers are created by "miktex links install" (admin mode);
# when they are missing the engines are called directly, which is what the
# launchers do. The LaTeX passes write .xdv, then dvipdfmx writes the .pdf.
param([string]$doc = "all")

# Native tools print notices on stderr (MiKTeX's "updates are out-of-sync");
# under "Stop" PowerShell 5.1 would turn those into terminating errors.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$miktex = Join-Path $env:LOCALAPPDATA "Programs\MiKTeX\miktex\bin\x64"
if (Test-Path (Join-Path $miktex "miktex.exe")) { $env:PATH = "$miktex;$env:PATH" }

function Resolve-Tool([string]$launcher, [string]$engine, [string[]]$engineArgs) {
    if (Get-Command $launcher -ErrorAction SilentlyContinue) { return @($launcher) }
    if (Get-Command $engine -ErrorAction SilentlyContinue) { return @($engine) + $engineArgs }
    throw "neither $launcher nor $engine found - point `$miktex at your MiKTeX bin\x64 or run: miktex packages install miktex-xetex-bin-x64-2.9"
}
$xelatex   = Resolve-Tool "xelatex"   "miktex-xetex"    @("-undump=xelatex")
$bibtex    = Resolve-Tool "bibtex"    "miktex-bibtex"   @()
$xdvipdfmx = Resolve-Tool "xdvipdfmx" "miktex-dvipdfmx" @()
Write-Host "Using: $($xelatex -join ' ') / $($bibtex -join ' ') / $($xdvipdfmx -join ' ')" -ForegroundColor DarkGray

# ($args is PowerShell's automatic variable, so the parameter is named toolArgs.)
function Run([string[]]$cmd, [string[]]$toolArgs) {
    $exe = $cmd[0]
    $all = @()
    if ($cmd.Count -gt 1) { $all += $cmd[1..($cmd.Count - 1)] }
    $all += $toolArgs
    & $exe @all | Out-Host      # tool output to the console, only the exit code returned
    return $LASTEXITCODE
}

Run @("initexmf") @("--set-config-value=[MPM]AutoInstall=1") | Out-Null

$docs = if ($doc -eq "all") { @("vizdom_report_en", "vizdom_report_vi", "vizdom_architecture_en", "vizdom_architecture_vi") } else { @($doc) }
$failed = @()

foreach ($d in $docs) {
    Write-Host "=== Building $d ===" -ForegroundColor Cyan
    if (-not (Test-Path "$d.tex")) { Write-Host "[SKIP] $d.tex not found" -ForegroundColor Yellow; continue }
    # xelatex, bibtex, xelatex x2 so references, ToC and citations settle.
    Run $xelatex @("-no-pdf", "-interaction=nonstopmode", "$d.tex") | Out-Null
    Run $bibtex  @($d) | Out-Null
    Run $xelatex @("-no-pdf", "-interaction=nonstopmode", "$d.tex") | Out-Null
    $rc = Run $xelatex @("-no-pdf", "-interaction=nonstopmode", "$d.tex")
    if (-not (Test-Path "$d.xdv") -or $rc -ne 0) {
        Write-Host "[ERROR] ${d}: LaTeX pass failed (exit $rc) - see ${d}.log" -ForegroundColor Red
        $failed += $d
        continue
    }
    $rc = Run $xdvipdfmx @("-o", "$d.pdf", "$d.xdv")
    if ($rc -ne 0) {
        Write-Host "[WARN] could not write $d.pdf (open in a viewer?) - writing ${d}_new.pdf" -ForegroundColor Yellow
        Run $xdvipdfmx @("-o", "${d}_new.pdf", "$d.xdv") | Out-Null
    }
    Write-Host "-> $d.pdf" -ForegroundColor Green
}

if ($failed.Count -gt 0) { Write-Host "FAILED: $($failed -join ', ')" -ForegroundColor Red; exit 1 }
