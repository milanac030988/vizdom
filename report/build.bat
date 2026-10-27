@echo off
setlocal enabledelayedexpansion
REM ============================================================
REM  VizDOM report build - all in one
REM
REM  Usage (double-click, or from a terminal in report\):
REM    build.bat                       build all four PDFs
REM    build.bat vizdom_report_en      build just one document
REM    build.bat figures    regenerate figures from PlantUML, then build all
REM
REM  Builds via .xdv then xdvipdfmx, so the LaTeX passes never touch the
REM  .pdf. If a .pdf is open in a viewer (locked), it writes <doc>_new.pdf
REM  instead of failing.
REM ============================================================
cd /d "%~dp0"

REM --- Put MiKTeX on PATH (installed here but not on PATH) ---
set "MIKTEX=C:\Users\ugc1hc\AppData\Local\Programs\MiKTeX\miktex\bin\x64"
if exist "%MIKTEX%\miktex.exe" set "PATH=%MIKTEX%;%PATH%"

REM --- Resolve the tools. xelatex.exe / bibtex.exe / xdvipdfmx.exe are thin
REM launchers that MiKTeX creates in its "links install" step, which needs admin
REM mode; after a user-mode-only setup or an out-of-sync update they are absent
REM while the engines (miktex-xetex.exe, ...) are present. Then call the engines
REM directly - it is exactly what the launchers do.
set "XELATEX=xelatex"
set "BIBTEX=bibtex"
set "XDVIPDFMX=xdvipdfmx"
where xelatex >nul 2>&1   || set "XELATEX=miktex-xetex -undump=xelatex"
where bibtex >nul 2>&1    || set "BIBTEX=miktex-bibtex"
where xdvipdfmx >nul 2>&1 || set "XDVIPDFMX=miktex-dvipdfmx"

where xelatex >nul 2>&1 || where miktex-xetex >nul 2>&1
if errorlevel 1 (
  echo [ERROR] neither xelatex nor miktex-xetex found on PATH.
  echo         Edit the MIKTEX line in this script to point at your MiKTeX bin\x64,
  echo         or install the xetex package: miktex packages install miktex-xetex-bin-x64-2.9
  pause
  exit /b 1
)
echo Using: %XELATEX% / %BIBTEX% / %XDVIPDFMX%

REM --- Allow MiKTeX to auto-install missing packages without prompting ---
initexmf --set-config-value="[MPM]AutoInstall=1" >nul 2>&1

set "DOCS=vizdom_report_en vizdom_report_vi vizdom_architecture_en vizdom_architecture_vi"

REM --- Optional figure regeneration ---
if /i "%~1"=="figures" (
  call :figures
) else (
  if not "%~1"=="" set "DOCS=%~1"
)

for %%D in (%DOCS%) do call :build %%D

echo.
echo ============================================================
echo  Done. PDFs in %cd%:
echo ============================================================
dir /b *.pdf 2>nul
echo.
pause
exit /b 0

REM ------------------------------------------------------------
:build
set "D=%~1"
echo.
echo ============================================================
echo   Building %D%
echo ============================================================
if not exist "%D%.tex" (
  echo [SKIP] %D%.tex not found
  goto :eof
)
REM LaTeX passes write only .xdv/.aux/.toc - never the .pdf, so an open
REM viewer can't block them. Three passes + bibtex so refs/ToC/citations settle.
%XELATEX% -no-pdf -interaction=nonstopmode "%D%.tex"
%BIBTEX% "%D%"
%XELATEX% -no-pdf -interaction=nonstopmode "%D%.tex"
%XELATEX% -no-pdf -interaction=nonstopmode "%D%.tex"

if not exist "%D%.xdv" (
  echo [ERROR] %D%.xdv not produced - see %D%.log for LaTeX errors.
  goto :eof
)

REM Convert .xdv -> .pdf. If the .pdf is locked (open in a viewer), fall back.
%XDVIPDFMX% -o "%D%.pdf" "%D%.xdv"
if errorlevel 1 (
  echo [WARN] Could not write %D%.pdf ^(is it open in a viewer?^).
  echo        Writing %D%_new.pdf instead - close the viewer and rerun to refresh %D%.pdf.
  %XDVIPDFMX% -o "%D%_new.pdf" "%D%.xdv"
)
goto :eof

REM ------------------------------------------------------------
:figures
echo.
echo === Regenerating figures from docs\diagrams ===
set "GRAPHVIZ_DOT=C:\Program Files\Graphviz\bin\dot.exe"
if not exist "figures" mkdir "figures"
if not exist "..\tools\plantuml.jar" (
  echo [WARN] ..\tools\plantuml.jar not found - skipping figure regen.
  goto :eof
)
for %%F in (system_overview architecture cv_pipeline_detail sequence component problem_space) do (
  echo   rendering %%F ...
  java -jar "..\tools\plantuml.jar" -tpng -o "%cd%\figures" "..\docs\diagrams\%%F.puml"
)
goto :eof
