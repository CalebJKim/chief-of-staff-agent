@echo off
setlocal
title Chief of Staff Credential Package
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\New-CredentialPackage.ps1"
pause
