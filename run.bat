@echo off
REM Script para ejecutar la aplicación aldlasforo localmente

cd /d "%~dp0"

REM Verificar que estamos en el directorio correcto
if not exist "aldlasforo\backend\main.py" (
    echo ERROR: No se encontró aldlasforo\backend\main.py
    echo Asegúrate de ejecutar este script desde D:\aldlas foro
    pause
    exit /b 1
)

REM Activar entorno virtual
call .venv\Scripts\activate.bat

REM Instalar/actualizar dependencias si es necesario
echo Verificando dependencias...
pip install -q -r aldlasforo\requirements.txt

REM Ejecutar la aplicación
echo.
echo ====================================
echo Iniciando aldlasforo en http://localhost:8000
echo ====================================
echo.

cd aldlasforo
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

pause
