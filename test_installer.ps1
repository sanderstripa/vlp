param(
    [string]$Setup = (Join-Path $PSScriptRoot 'release\LocalDub-0.1.0-Setup.exe'),
    [string]$InstallPath = (Join-Path $PSScriptRoot 'installer-test-install'),
    [string]$Evidence = (Join-Path $PSScriptRoot 'evidence\installer-test.json')
)
$ErrorActionPreference = 'Stop'
$InstallPath = [IO.Path]::GetFullPath($InstallPath)
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalDub'
$shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'LocalDub'
if ((Test-Path $InstallPath) -or (Test-Path $key) -or (Test-Path $shortcut)) {
    throw 'Refusing to overwrite an existing LocalDub installation, shortcut, or test folder.'
}
$savedData = $env:LOCALDUB_DATA
$result = @{}
try {
    $env:LOCALDUB_DATA = Join-Path (Split-Path $InstallPath) 'installer-test-cache'
    $process = Start-Process -FilePath $Setup -ArgumentList @('/S',"/D=$InstallPath") -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) { throw "Installer failed: $($process.ExitCode)" }
    $result.install_exit = $process.ExitCode
    $exe = Join-Path $InstallPath 'LocalDub.exe'
    if (-not (Test-Path $exe)) { throw 'Installed EXE missing' }
    $result.uninstall_command = (Get-ItemProperty $key).UninstallString
    if ($result.uninstall_command -ne ('"' + (Join-Path $InstallPath 'Uninstall.exe') + '"')) { throw 'Invalid UninstallString' }
    $smoke = Join-Path (Split-Path $Evidence) 'installed-exe-smoke.json'
    $process = Start-Process -FilePath $exe -ArgumentList @('--smoke',$smoke,'--smoke-full') -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) { throw 'Installed player failed' }
    $snapshot = Get-Content -LiteralPath $smoke -Raw | ConvertFrom-Json
    if ($snapshot.error -or $snapshot.voice_backend -ne 'wasapi' -or $snapshot.translated_cues -ne 3) { throw 'Installed player smoke failed' }
    $result.smoke_passed = $true
    $result.installed_exe_sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
    $sentinel = Join-Path $InstallPath 'user-file-preserved.txt'
    Set-Content -LiteralPath $sentinel -Value 'unrelated user file'
    $process = Start-Process -FilePath (Join-Path $InstallPath 'Uninstall.exe') -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden
    for ($i=0; $i -lt 100 -and (Test-Path $exe); $i++) { Start-Sleep -Milliseconds 100 }
    if ((Test-Path $exe) -or (Test-Path $key) -or (Test-Path $shortcut)) { throw 'Uninstall did not complete' }
    if (-not (Test-Path $sentinel)) { throw 'Uninstaller deleted an unrelated file' }
    $result.uninstall_passed = $true
    $result.unrelated_file_preserved = $true
    Remove-Item -LiteralPath $sentinel
    if (-not (Get-ChildItem -LiteralPath $InstallPath -Force)) { Remove-Item -LiteralPath $InstallPath }
    $result.passed = $true
} finally {
    $env:LOCALDUB_DATA = $savedData
    $result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $Evidence -Encoding utf8
}
$result | ConvertTo-Json
