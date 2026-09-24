@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 encoder_diagnostics.py %*
) else (
    python encoder_diagnostics.py %*
)

echo.
pause
