@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
title Alter Aeon Help Corpus Audit
cd /d "%~dp0.."

set "PYTHON_EXE=D:\altar aeon\Mush-Z\worlds\plugins\translation_bridge\runtime\python\python.exe"
if exist "%PYTHON_EXE%" goto run

set "PYTHON_EXE=%~dp0..\src\mush-z\worlds\plugins\translation_bridge\runtime\python\python.exe"
if exist "%PYTHON_EXE%" goto run

echo Python runtime was not found.
echo Expected it under the installed Translation Bridge runtime.
goto finish

:run
"%PYTHON_EXE%" "%~dp0audit_official_help_corpus.py"
set "AUDIT_EXIT=%ERRORLEVEL%"

:finish
pause >nul
endlocal
