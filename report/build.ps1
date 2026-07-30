# Build the VizDOM reports to PDF with XeLaTeX.
#   powershell -ExecutionPolicy Bypass -File build.ps1            # builds all three
#   powershell -ExecutionPolicy Bypass -File build.ps1 vizdom_report_en   # builds one
param([string]$doc = "all")

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$docs = if ($doc -eq "all") { @("vizdom_report_en", "vizdom_report_vi", "vizdom_architecture_en", "vizdom_architecture_vi") } else { @($doc) }

foreach ($d in $docs) {
    Write-Host "=== Building $d ===" -ForegroundColor Cyan
    if (Get-Command latexmk -ErrorAction SilentlyContinue) {
        latexmk -xelatex -interaction=nonstopmode "$d.tex"
    } else {
        # Manual sequence: xelatex, bibtex, xelatex x2 (PowerShell has no &&)
        xelatex -interaction=nonstopmode "$d.tex"
        bibtex $d
        xelatex -interaction=nonstopmode "$d.tex"
        xelatex -interaction=nonstopmode "$d.tex"
    }
    Write-Host "-> $d.pdf" -ForegroundColor Green
}
