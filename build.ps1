$ErrorActionPreference = 'Stop'
$python = if ($env:GLOW_PYTHON) { $env:GLOW_PYTHON } else { 'python' }
& $python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $python -m PyInstaller --noconfirm --clean --onedir --windowed --name GlowLetters --paths src --collect-all eccodes --collect-all gribapi --add-data 'src/city-geo.json;.' src/glow_app.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
$compiler = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Install Inno Setup 6 before building the wizard installer' }
& $compiler 'installer\GlowLetters.iss'
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
