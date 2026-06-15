# Rubble Language Installer for Windows
# Run this in PowerShell as Administrator:
#
#   irm https://raw.githubusercontent.com/TM1988/Rubble/main/install.ps1 | iex
#
# What this does:
#   1. Installs Python 3.11 (if not present)
#   2. Installs LLVM / clang (if not present)
#   3. Clones the Rubble repo (or updates it)
#   4. Installs the `rubble` command via pip
#   5. Adds everything to your PATH permanently

param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Rubble"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host ""
    Write-Host "  --> $msg" -ForegroundColor Cyan
}

function Write-Ok($msg) {
    Write-Host "  [OK] $msg" -ForegroundColor Green
}

function Write-Fail($msg) {
    Write-Host "  [!!] $msg" -ForegroundColor Red
    exit 1
}

function Add-ToPath($dir) {
    $current = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    if ($current -notlike "*$dir*") {
        [System.Environment]::SetEnvironmentVariable("PATH", "$current;$dir", "User")
        $env:PATH += ";$dir"
        Write-Ok "Added to PATH: $dir"
    } else {
        Write-Ok "Already in PATH: $dir"
    }
}

Write-Host ""
Write-Host "  Rubble Language Installer" -ForegroundColor Yellow
Write-Host "  =========================" -ForegroundColor Yellow
Write-Host ""

# ── 1. Check / install Python ─────────────────────────────────────────────
Write-Step "Checking Python..."
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Step "Python not found. Downloading Python 3.11..."
    $pyInstaller = "$env:TEMP\python_installer.exe"
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" `
        -OutFile $pyInstaller -UseBasicParsing
    Write-Step "Installing Python 3.11 (silent)..."
    Start-Process -FilePath $pyInstaller -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1" -Wait
    Remove-Item $pyInstaller
    # Refresh PATH
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","User") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","Machine")
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { Write-Fail "Python install failed. Please install manually: https://python.org" }
    Write-Ok "Python installed"
} else {
    Write-Ok "Python found: $($python.Source)"
}

# ── 2. Check / install LLVM (clang) ───────────────────────────────────────
Write-Step "Checking clang / LLVM..."
$clang = Get-Command clang -ErrorAction SilentlyContinue
$clangPath = "C:\Program Files\LLVM\bin"
if (-not $clang -and -not (Test-Path "$clangPath\clang.exe")) {
    Write-Step "clang not found. Downloading LLVM 18..."
    $llvmInstaller = "$env:TEMP\llvm_installer.exe"
    Invoke-WebRequest -Uri "https://github.com/llvm/llvm-project/releases/download/llvmorg-18.1.8/LLVM-18.1.8-win64.exe" `
        -OutFile $llvmInstaller -UseBasicParsing
    Write-Step "Installing LLVM 18 (this may take a minute)..."
    Start-Process -FilePath $llvmInstaller -ArgumentList "/S" -Wait
    Remove-Item $llvmInstaller
    Add-ToPath $clangPath
    Write-Ok "LLVM installed"
} else {
    if (Test-Path "$clangPath\clang.exe") { Add-ToPath $clangPath }
    Write-Ok "clang found"
}

# ── 3. Clone or update Rubble repo ────────────────────────────────────────
Write-Step "Setting up Rubble in $InstallDir..."
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
    if (Test-Path "$InstallDir\.git") {
        Write-Step "Updating existing Rubble installation..."
        Set-Location $InstallDir
        git pull --quiet
    } else {
        git clone --quiet https://github.com/TM1988/Rubble.git $InstallDir
    }
    Write-Ok "Rubble repo ready"
} else {
    # No git — download zip instead
    Write-Step "git not found. Downloading Rubble as zip..."
    $zipPath = "$env:TEMP\rubble.zip"
    Invoke-WebRequest -Uri "https://github.com/TM1988/Rubble/archive/refs/heads/main.zip" `
        -OutFile $zipPath -UseBasicParsing
    if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
    Expand-Archive -Path $zipPath -DestinationPath "$env:TEMP\rubble_extract"
    Move-Item "$env:TEMP\rubble_extract\Rubble-main" $InstallDir
    Remove-Item $zipPath
    Remove-Item -Recurse -Force "$env:TEMP\rubble_extract" -ErrorAction SilentlyContinue
    Write-Ok "Rubble downloaded"
}

# ── 4. Install rubble command via pip ─────────────────────────────────────
Write-Step "Installing rubble command..."
Set-Location $InstallDir
python -m pip install -e . --quiet
if ($LASTEXITCODE -ne 0) { Write-Fail "pip install failed" }

# Make sure pip scripts folder is on PATH
$pipScripts = python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
Add-ToPath $pipScripts

Write-Ok "rubble command installed"

# ── 5. Done ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  =================================" -ForegroundColor Green
Write-Host "  Rubble installed successfully!" -ForegroundColor Green
Write-Host "  =================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Open a NEW terminal and try:" -ForegroundColor White
Write-Host "    rubble examples\hello_world.rbl" -ForegroundColor Yellow
Write-Host ""
Write-Host "  You may need to restart your terminal for PATH changes to take effect." -ForegroundColor Gray
Write-Host ""
