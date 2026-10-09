@echo off
setlocal
title Mush-Z Translation Release Publisher
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\publish_release.ps1"
echo.
if errorlevel 1 (
  echo RELEASE FAILED. Nothing else will be uploaded.
) else (
  echo RELEASE COMPLETED AND PLAYER UPDATE CHECK PASSED.
)
pause
