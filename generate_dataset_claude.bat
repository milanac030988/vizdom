@echo off
REM Generate synthetic UI dataset using Claude Code as UI designer
REM Usage:
REM   generate_dataset_claude.bat                    (10 samples)
REM   generate_dataset_claude.bat 20                 (20 samples)
REM   generate_dataset_claude.bat 5 "car infotainment"  (5 car UIs)

cd /d "%~dp0"

set NUM=%1
if "%NUM%"=="" set NUM=10

set APP_TYPE=%2

if "%APP_TYPE%"=="" (
    "D:\Python\python39\python.exe" scripts/data_prep/generate_with_claude.py -n %NUM%
) else (
    "D:\Python\python39\python.exe" scripts/data_prep/generate_with_claude.py -n %NUM% --app-type %APP_TYPE%
)
