@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-docker.ps1" %*
endlocal
