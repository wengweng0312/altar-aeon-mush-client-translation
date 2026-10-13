@echo off
setlocal
cd /d "%~dp0.."
echo Alter Aeon translation trace audit
echo This tool is read-only and does not call any translation service.
echo.
where py.exe >nul 2>&1
if not errorlevel 1 (
  py.exe -3 tools\audit_translation_trace.py --replay-lmt
) else (
  python.exe tools\audit_translation_trace.py --replay-lmt
)
if errorlevel 1 (
  echo.
  echo AUDIT FAILED. Give the text above to Codex.
) else (
  echo.
  echo AUDIT COMPLETED. Tell Codex: Translation trace audit completed.
)
pause
endlocal
