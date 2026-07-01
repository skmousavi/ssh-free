#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$InstallDir = Join-Path $env:LOCALAPPDATA "ssh-free"
$LauncherDir = Join-Path $InstallDir "launchers"

Write-Host "[+] Removing ssh-free from Windows..." -ForegroundColor Green

if (Test-Path $InstallDir) {
    Remove-Item -Recurse -Force $InstallDir
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -and $LauncherDir) {
    $newPath = ($userPath -split ';' | Where-Object { $_ -and $_ -ne $LauncherDir }) -join ';'
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
}

[Environment]::SetEnvironmentVariable("SSH_FREE_ROOT", $null, "User")
Write-Host "[+] Uninstall complete" -ForegroundColor Green
