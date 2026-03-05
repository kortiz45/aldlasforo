# Script PowerShell para ejecutar aldlasforo

param(
    [string]$Host = "0.0.0.0",
    [int]$Port = 8000,
    [switch]$Reload = $true
)

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

# Verificar que estamos en el directorio correcto
if (-not (Test-Path "aldlasforo\backend\main.py")) {
    Write-Host "ERROR: No se encontró aldlasforo\backend\main.py" -ForegroundColor Red
    Write-Host "Asegúrate de ejecutar este script desde D:\aldlas foro" -ForegroundColor Red
    exit 1
}

# Activar entorno virtual
& ".\.venv\Scripts\Activate.ps1"

# Instalar/actualizar dependencias
Write-Host "Verificando dependencias..." -ForegroundColor Yellow
pip install -q -r aldlasforo\requirements.txt

# Ejecutar la aplicación
Write-Host ""
Write-Host "====================================" -ForegroundColor Green
Write-Host "Iniciando aldlasforo" -ForegroundColor Green
Write-Host "URL: http://$($Host):$Port" -ForegroundColor Green
Write-Host "====================================" -ForegroundColor Green
Write-Host ""

Set-Location aldlasforo
$reloadFlag = if ($Reload) { "--reload" } else { "" }
python -m uvicorn backend.main:app --host $Host --port $Port $reloadFlag
