# ssh-free Windows installer
# Prefer: install.bat  (uses Python only, no PowerShell required)
# Or:     powershell -ExecutionPolicy Bypass -File .\install.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-Python {
    foreach ($cmd in @("python", "py", "python3")) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            if ($cmd -eq "py") { return @("py", "-3") }
            return @($cmd)
        }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Host "[ERROR] Python 3 not found" -ForegroundColor Red
    exit 1
}

& $py[0] $py[1..($py.Length-1)] (Join-Path $RepoRoot "lib\windows_setup.py") --install $RepoRoot
exit $LASTEXITCODE
