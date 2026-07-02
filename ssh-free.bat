@echo off
setlocal
cd /d "%~dp0"
set "SSH_FREE_ROOT=%~dp0"
if "%SSH_FREE_ROOT:~-1%"=="\" set "SSH_FREE_ROOT=%SSH_FREE_ROOT:~0,-1%"

where python >nul 2>&1 && set "PY=python" && goto :run
where py >nul 2>&1 && set "PY=py -3" && goto :run

echo [ERROR] Python not found. Install from https://python.org
exit /b 1

:run
%PY% "%SSH_FREE_ROOT%\bin\ssh-free" %*
