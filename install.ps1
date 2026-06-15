# Rubble one-time install script
# Run this once: .\install.ps1
# After this, just use:  rubblec main.rbl

Write-Host "Installing Rubble compiler..." -ForegroundColor Cyan

pip install -e . --quiet

if ($LASTEXITCODE -eq 0) {
    Write-Host "Done! You can now use:" -ForegroundColor Green
    Write-Host "  rubblec main.rbl            # emit LLVM IR" -ForegroundColor White
    Write-Host "  rubblec main.rbl --build    # compile to native binary (requires clang)" -ForegroundColor White
    Write-Host "  rubblec main.rbl --check    # type-check only" -ForegroundColor White
} else {
    Write-Host "Install failed. Make sure Python and pip are available." -ForegroundColor Red
}
