$ErrorActionPreference = "Stop"

$python = "python"
$venv = ".venv-build"

if (-not (Test-Path $venv)) {
    & $python -m venv $venv
}

$venvPython = Join-Path $venv "Scripts\python.exe"
# pip y PyInstaller escriben su progreso en stderr. Con ErrorActionPreference=Stop,
# Windows PowerShell 5.1 aborta el script, asi que aqui lo bajamos y revisamos $LASTEXITCODE.
$ErrorActionPreference = "Continue"

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "Fallo al instalar las dependencias de build." }
& $venvPython -m PyInstaller --noconfirm Proxynas.spec
if ($LASTEXITCODE -ne 0) { throw "Fallo PyInstaller." }

# Nunca publicar el SDK propietario de Blackmagic, aunque exista en portable/ local.
$releaseDir = "dist\Proxynas"
$forbidden = Get-ChildItem -LiteralPath $releaseDir -Recurse -File | Where-Object {
    $_.Name -match '(?i)blackmagic|decodercuda|decoderopencl|instructionsetservices' -or
    $_.FullName -match '(?i)[\\/]portable[\\/]sdk[\\/]'
}
if ($forbidden -or (Test-Path -LiteralPath "$releaseDir\_internal\portable\sdk")) {
    $forbidden | ForEach-Object { Write-Error "SDK prohibido en el build: $($_.FullName)" }
    throw "Build bloqueado: contiene archivos del SDK de Blackmagic."
}

Write-Host ""
Write-Host "Build listo: dist\Proxynas\Proxynas.exe"
Write-Host "La carpeta dist\Proxynas contiene el ejecutable y todas las dependencias empaquetadas."
