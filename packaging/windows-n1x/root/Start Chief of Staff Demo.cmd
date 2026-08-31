@echo off
setlocal
title Chief of Staff Demo
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-Demo.ps1"
if errorlevel 1 pause
