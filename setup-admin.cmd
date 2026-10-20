@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" manage_users.py init-admin
) else (
  py -3 manage_users.py init-admin
)
if errorlevel 1 pause
