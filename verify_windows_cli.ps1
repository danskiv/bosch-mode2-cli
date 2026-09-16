$ErrorActionPreference = 'Stop'
$Root = 'C:\Users\tech\Documents\GitHub\bosch-mode2-cli'
Set-Location -LiteralPath $Root
$env:PYTHONPATH = (Join-Path $Root 'src')
$python = Join-Path $Root '.venv\Scripts\python.exe'
& $python -c "import bosch_mode2_cli.cli as c; print(c.__file__); print('SOURCE_IMPORT_OK')"
& $python -m bosch_mode2_cli.cli -h
if ($LASTEXITCODE -ne 0) { throw "CLI help failed" }
