@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0install-model.ps1"
pause
