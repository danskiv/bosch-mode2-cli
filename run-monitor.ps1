# Run the read-only Bosch Solution 2000 CLI monitor on Windows.
# B426 IP address, port, and visible code are requested on every run.
# Press Enter to keep saved values, or type replacements.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root
$env:PYTHONPATH = (Join-Path $Root 'src')
$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Windows venv not found at $python"
}
& $python -m bosch_mode2_cli.cli monitor `
    --plain `
    @args
exit $LASTEXITCODE
