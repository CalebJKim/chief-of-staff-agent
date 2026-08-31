@echo off
setlocal
title Repair Chief of Staff Demo
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Setup-Demo.ps1" -Repair
if errorlevel 1 pause
