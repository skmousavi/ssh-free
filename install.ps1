# ssh-free Windows installer (like install.sh on Linux)
# Usage: powershell -ExecutionPolicy Bypass -File .\install.ps1
#    or: install.bat

$ErrorActionPreference = "Stop"

$Version = "3.0.0"
$InstallDir = Join-Path $env:LOCALAPPDATA "ssh-free"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BinLinks = @("ssh-free", "ssh-free-stop", "doctor", "status", "tui")

function Info($msg) { Write-Host "[+] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

function Find-Python {
    foreach ($cmd in @("python", "py", "python3")) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) {
            if ($cmd -eq "py") { return @("py", "-3") }
            return @($cmd)
        }
    }
    return $null
}

function Invoke-Python($PyCmd, $Arguments) {
    $all = @()
    $all += $PyCmd
    $all += $Arguments
    & $all[0] $all[1..($all.Length - 1)]
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "Command failed: $($all -join ' ') (exit $LASTEXITCODE)"
    }
}

try {
    Info "Installing ssh-free v$Version for Windows"
    Info "Source: $RepoRoot"

    if (-not (Test-Path (Join-Path $RepoRoot "bin\ssh-free"))) {
        Fail "Run install.ps1 from the ssh-free project folder"
    }

    $pyCmd = Find-Python
    if (-not $pyCmd) {
        Fail "Python 3 not found. Install from https://python.org (check Add to PATH)"
    }

    # Step 1: prerequisites (Python, pip, PyYAML, OpenSSH) — like install.sh apt deps
    Info "Checking and installing prerequisites..."
    $setupScript = Join-Path $RepoRoot "lib\windows_setup.py"
    Invoke-Python $pyCmd @($setupScript, "--ensure-deps")

    # Step 2: copy files
    Info "Copying files to $InstallDir"
    if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

    $exclude = @(".git", "__pycache__", "launchers")
    Get-ChildItem -Path $RepoRoot -Force | Where-Object {
        $exclude -notcontains $_.Name
    } | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination $InstallDir -Recurse -Force
    }

    New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "logs") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "runtime") | Out-Null

    # Step 3: PATH launchers (always run prereq first)
    $LauncherDir = Join-Path $InstallDir "launchers"
    New-Item -ItemType Directory -Force -Path $LauncherDir | Out-Null

    $pyLine = if ($pyCmd.Length -gt 1) { "$($pyCmd[0]) $($pyCmd[1])" } else { $pyCmd[0] }

    foreach ($name in $BinLinks) {
        $pyScript = Join-Path $InstallDir "bin\$name"
        @"
@echo off
setlocal
set "SSH_FREE_ROOT=$InstallDir"
call "$InstallDir\win-prereq.bat" || exit /b 1
$pyLine "$pyScript" %*
"@ | Set-Content -Path (Join-Path $LauncherDir "$name.cmd") -Encoding ASCII
    }

    # Copy win-prereq to install dir
    Copy-Item (Join-Path $RepoRoot "win-prereq.bat") (Join-Path $InstallDir "win-prereq.bat") -Force

    # Step 4: user PATH
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $userPath) { $userPath = "" }
    if ($userPath -notlike "*$LauncherDir*") {
        Info "Adding to user PATH: $LauncherDir"
        if ($userPath -and -not $userPath.EndsWith(";")) {
            $userPath = "$userPath;"
        }
        [Environment]::SetEnvironmentVariable("Path", "$userPath$LauncherDir", "User")
    }

    [Environment]::SetEnvironmentVariable("SSH_FREE_ROOT", $InstallDir, "User")
    $env:Path = "$env:Path;$LauncherDir"
    $env:SSH_FREE_ROOT = $InstallDir

    # Step 5: verify (like doctor at end of install)
    Info "Verifying installation..."
    Invoke-Python $pyCmd @($setupScript, "--verify", $InstallDir)

    Info "Installation complete!"
    Write-Host ""
    Write-Host "  Close and reopen CMD, then:"
    Write-Host "    ssh-free administrator@192.168.0.9"
    Write-Host ""
    Write-Host "  Or from this folder now:"
    Write-Host "    .\ssh-free.bat administrator@192.168.0.9"
    Write-Host ""
    Write-Host "  v2rayN must be running (127.0.0.1:10808)"
    Write-Host ""
}
catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
