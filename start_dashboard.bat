@echo off
REM VizDOM Dashboard
REM Usage: start_dashboard.bat

cd /d "%~dp0"
call "%~dp0python_env.bat" || exit /b 1
"%VIZDOM_PY%" -m streamlit run tools/dashboard/app.py --server.port 8501
