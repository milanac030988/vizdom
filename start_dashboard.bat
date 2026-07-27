@echo off
REM VizDOM Dashboard
REM Usage: start_dashboard.bat

cd /d "%~dp0"
"D:\Python\python39\python.exe" -m streamlit run tools/dashboard/app.py --server.port 8501
