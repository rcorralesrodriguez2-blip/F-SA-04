@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
%PY% --version >nul 2>nul
if errorlevel 1 (echo ERROR: Instale Python 3 y agreguelo al PATH.& pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv
    if errorlevel 1 (echo No se pudo crear el entorno virtual.& pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo Error instalando las dependencias. Compruebe la conexion a Internet.& pause & exit /b 1)
echo Abra http://127.0.0.1:5000 en el navegador.
".venv\Scripts\python.exe" app.py
pause
