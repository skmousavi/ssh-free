@echo off
setlocal
cd /d "%~dp0"
set "SSH_FREE_ROOT=%~dp0"
if "%SSH_FREE_ROOT:~-1%"=="\" set "SSH_FREE_ROOT=%SSH_FREE_ROOT:~0,-1%"

call "%~dp0win-prereq.bat" || exit /b 1

where python >nul 2>&1 && set "PY=python" && goto :run
set "PY=py -3"

:run
%PY% "%SSH_FREE_ROOT%\bin\ssh-free-stop" %*
