@echo off
setlocal
"%~dp0runtime\python\python.exe" "%~dp0build_translation_package.py" %*
if errorlevel 1 pause
