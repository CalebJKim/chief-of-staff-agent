@echo off
powershell.exe -NoProfile -File "%~dp0setup\perplexity\launch.ps1"
if errorlevel 1 pause
