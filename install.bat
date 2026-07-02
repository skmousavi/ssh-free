@echo off
title ssh-free Windows Installer
cd /d "%~dp0"
echo.
echo  ssh-free Windows Installer
echo  ========================
echo.

set "ERR=1"

where python >nul 2>&1 && (
    python "%~dp0lib\windows_setup.py" --install "%~dp0"
    if not errorlevel 1 set "ERR=0"
    goto :done
)

where py >nul 2>&1 && (
    py -3 "%~dp0lib\windows_setup.py" --install "%~dp0"
    if not errorlevel 1 set "ERR=0"
    goto :done
)

echo [ERROR] Python 3 not found.
echo         Install from https://python.org and check "Add to PATH"
goto :end

:done
if "%ERR%"=="1" (
    echo.
    echo [ERROR] Installation failed. See messages above.
) else (
    echo.
    echo [OK] Done. Close this window, open a NEW CMD, then run ssh-free.
)

:end
echo.
pause
exit /b %ERR%
