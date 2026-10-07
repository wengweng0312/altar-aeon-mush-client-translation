@echo off
setlocal
cd /d "%~dp0"
%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_translation.ps1"
set "update_exit=%ERRORLEVEL%"
echo.
if not "%update_exit%"=="0" echo Update failed. Existing translation files were preserved.
pause
exit /b %update_exit%
