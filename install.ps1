#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$Version = "3.0.0"
$InstallDir = Join-Path $env:LOCALAPPDATA "ssh-free"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$BinLinks = @("ssh-free", "ssh-free-stop", "doctor", "status", "tui")

function Info($msg) { Write-Host "[+] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

Info "Installing ssh-free v$Version for Windows"

# Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Fail "Python 3 not found. Install from https://python.org" }

python -c "import yaml" 2>$null
if ($LASTEXITCODE -ne 0) {
    Info "Installing PyYAML..."
    python -m pip install --user pyyaml
    python -c "import yaml" 2>$null
    if ($LASTEXITCODE -ne 0) { Fail "PyYAML required: pip install pyyaml" }
}
Info "Python dependency OK (yaml)"

# OpenSSH client
$sshExe = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
if (-not (Test-Path $sshExe)) {
    Warn "OpenSSH client not found."
    Warn "Settings -> Apps -> Optional features -> Add OpenSSH Client"
}

# Copy files
Info "Copying files to $InstallDir"
if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$exclude = @(".git", "__pycache__")
Get-ChildItem -Path $RepoRoot -Force | Where-Object {
    $exclude -notcontains $_.Name
} | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination $InstallDir -Recurse -Force
}

New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "runtime") | Out-Null

# User PATH launcher directory
$LauncherDir = Join-Path $InstallDir "launchers"
New-Item -ItemType Directory -Force -Path $LauncherDir | Out-Null

foreach ($name in $BinLinks) {
    $cmdName = "$name.cmd"
    $src = Join-Path $InstallDir "bin\$cmdName"
    if (-not (Test-Path $src)) {
        $pyScript = Join-Path $InstallDir "bin\$name"
        @"
@echo off
setlocal
set SSH_FREE_ROOT=$InstallDir
python "$pyScript" %*
"@ | Set-Content -Path (Join-Path $LauncherDir "$name.cmd") -Encoding ASCII
    } else {
        Copy-Item $src (Join-Path $LauncherDir "$name.cmd") -Force
    }
}

# Add launchers to user PATH
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$LauncherDir*") {
    Info "Adding to user PATH: $LauncherDir"
    [Environment]::SetEnvironmentVariable(
        "Path",
        "$userPath;$LauncherDir",
        "User"
    )
}

[Environment]::SetEnvironmentVariable("SSH_FREE_ROOT", $InstallDir, "User")

Info "Installation complete!"
Write-Host ""
Write-Host "  Restart terminal, then:"
Write-Host "  ssh-free root@YOUR_SERVER"
Write-Host "  ssh-free-stop"
Write-Host "  doctor"
Write-Host ""
Write-Host "  v2rayN must be running (127.0.0.1:10808)"
Write-Host ""
