param([string]$Python = 'python', [switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed: $LASTEXITCODE" } }
if (-not (Test-Path '.venv\Scripts\python.exe')) { & $Python -m venv .venv; Check-Exit }
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not $SkipInstall) { & $py -m pip install -r requirements-lock.txt; Check-Exit }
& $py -X utf8 setup_components.py
Check-Exit
& $py -m PyInstaller --noconfirm --clean --onedir --windowed --name LocalDub --distpath dist --workpath build --collect-all ctranslate2 --collect-all faster_whisper --collect-all sentencepiece --collect-all av --collect-all onnxruntime --collect-all py7zr --exclude-module PIL --exclude-module soundcard app.py
Check-Exit
$dest = Join-Path $PSScriptRoot 'dist\LocalDub'
Copy-Item native,models -Destination $dest -Recurse -Force
Copy-Item component-manifest.json,test-video.mp4,test-video.srt,README.md,THIRD_PARTY.md -Destination $dest -Force
Write-Host "Ready: $dest\LocalDub.exe"
