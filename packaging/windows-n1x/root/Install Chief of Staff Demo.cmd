@echo off
setlocal
title Chief of Staff Demo Setup
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Setup-Demo.ps1"
if errorlevel 1 (
  echo.
  echo Setup did not complete. Review the error above, then run this installer again.
  pause
)
