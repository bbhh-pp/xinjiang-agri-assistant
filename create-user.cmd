@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo 用法: create-user.cmd 用户名
  exit /b 1
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" manage_users.py create-user "%~1"
) else (
  py -3 manage_users.py create-user "%~1"
)
if errorlevel 1 pause
