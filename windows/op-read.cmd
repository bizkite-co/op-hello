@echo off
REM Windows entry: op-read.cmd "op://Vault/Item/field" ["op://Vault/Item/other"]
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0op-read.ps1" %*
exit /b %ERRORLEVEL%
