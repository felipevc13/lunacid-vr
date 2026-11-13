# Lunacid VR for Windows: from nothing to the game on your Quest.
#
# Open PowerShell (press the Windows key, type PowerShell, press Enter) and paste this line:
#
#   irm https://raw.githubusercontent.com/felipevc13/lunacid-vr/main/setup.ps1 | iex
#
# Inside a copy of this repository you can also run:  powershell -ExecutionPolicy Bypass -File .\setup.ps1
#
# It installs Git and Python when missing (winget, Microsoft's installer that comes with Windows), gets this
# project, and hands over to "lunacid_vr.py start", which does the rest and asks only what only you can answer.
# Run it again at any time: finished steps are skipped.

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/felipevc13/lunacid-vr.git"
function Say($text) { Write-Host $text -ForegroundColor Cyan }

function Refresh-Path {
    # Programs installed a moment ago are found without reopening the window.
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

function Have($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

function Install-Package($id, $name) {
    Say "Installing $name (Windows may ask for permission: choose Yes)..."
    winget install --id $id -e --silent --accept-source-agreements --accept-package-agreements
    Refresh-Path
}

function Find-Python {
    # Only the py launcher, checked by what it prints: Windows' own "python" may just open the Microsoft Store.
    if (Have "py") {
        $v = (& py -3 --version 2>&1) | Out-String
        if ($v -match "Python 3\.(\d+)" -and [int]$Matches[1] -ge 9) { return "py" }
    }
    foreach ($dir in Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Directory -ErrorAction SilentlyContinue) {
        $exe = Join-Path $dir.FullName "python.exe"
        if (Test-Path $exe) { return $exe }
    }
    return $null
}

Say "Lunacid VR: getting this computer ready."

if (-not (Have "winget")) {
    Say "This needs Microsoft's App Installer (it brings winget). Opening the Microsoft Store: install it, then paste the same line again."
    Start-Process "ms-windows-store://pdp/?productid=9NBLGGH4NNS1"
    return
}

if (-not (Have "git")) { Install-Package "Git.Git" "Git" }
if (-not (Have "git")) {
    Say "Git did not install. Close this window, open PowerShell again and paste the same line."
    return
}

$Python = Find-Python
if (-not $Python) {
    Install-Package "Python.Python.3.12" "Python"
    $Python = Find-Python
}
if (-not $Python) {
    Say "Python did not install. Close this window, open PowerShell again and paste the same line."
    return
}

# This project: the copy this script is in, or one in your user folder (cloned the first time, updated after).
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "lunacid_vr.py"))) {
    $Dir = $PSScriptRoot
} else {
    $Dir = Join-Path $HOME "lunacid-vr"
    if (Test-Path (Join-Path $Dir ".git")) {
        git -C $Dir pull --ff-only
    } else {
        Say "Downloading Lunacid VR..."
        git clone $RepoUrl $Dir
    }
}

Set-Location $Dir
if ($Python -eq "py") { & py -3 "$Dir\lunacid_vr.py" start } else { & $Python "$Dir\lunacid_vr.py" start }
