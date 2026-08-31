@echo off
setlocal
title Finalize Chief of Staff Demo
pushd "%TEMP%"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Finalize-Demo.ps1"
if errorlevel 1 pause
