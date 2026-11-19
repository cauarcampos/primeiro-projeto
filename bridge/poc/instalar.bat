@echo off
REM BRIDGE - instalacao (rode uma vez)
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1
where py >/dev/null 2>/dev/null && (py -3.12 -m venv .venv) || (python -m venv .venv)
if not exist .venv\Scripts\activate.bat (
  echo Nao foi possivel criar o ambiente Python. Instale o Python 3.12 de python.org e marque "Add python.exe to PATH".
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -e .[dev] || (echo Falha ao instalar dependencias. & pause & exit /b 1)
python -m bridge_poc.modelos || (echo Falha ao baixar modelos. & pause & exit /b 1)
python -m bridge_poc --diagnostico
echo.
echo Instalacao concluida. Para usar: iniciar.bat
pause
