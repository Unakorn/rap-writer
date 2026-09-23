@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" rap_writer.py
) else (
  py -3.13 rap_writer.py
)
if errorlevel 1 pause
