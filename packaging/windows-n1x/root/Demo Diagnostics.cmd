@echo off
setlocal
title Chief of Staff Demo Diagnostics
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Validate-Demo.ps1" -StartServer
pause
