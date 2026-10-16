@echo off
cd /d "%~dp0"
if exist "dist\LocalDub\LocalDub.exe" (start "" "dist\LocalDub\LocalDub.exe" & exit /b)
if exist ".venv\Scripts\pythonw.exe" (start "" ".venv\Scripts\pythonw.exe" "app.py" & exit /b)
echo Run build.ps1 first, or use the ready Windows package.
pause
