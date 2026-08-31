@echo off
setlocal
title Reset Chief of Staff Demo
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Reset-Demo.ps1"
if errorlevel 1 pause
