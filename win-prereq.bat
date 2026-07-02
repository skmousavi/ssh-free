@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

where python >nul 2>&1 && set "PY=python" && goto :run
where py >nul 2>&1 && set "PY=py -3" && goto :run

echo [ERROR] Python 3 not found.
echo         Install from https://python.org and check "Add to PATH"
exit /b 1

:run
%PY% "%ROOT%\lib\windows_setup.py" --ensure-deps
exit /b %ERRORLEVEL%
