@echo off
setlocal
set "SSH_FREE_ROOT=%~dp0.."
set "SSH_FREE_ROOT=%SSH_FREE_ROOT:~0,-1%"
python "%SSH_FREE_ROOT%\bin\ssh-free" %*
