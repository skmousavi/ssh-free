@echo off
title ssh-free Windows Installer
cd /d "%~dp0"
echo.
echo  ssh-free Windows Installer
echo  ========================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
