@echo off
REM BRIDGE - reconhecimento especializado em ucraniano (Parakeet UK). Rode depois do instalar.bat.
REM Uso: instalar_ucraniano.bat        (processa na CPU, download menor)
REM      instalar_ucraniano.bat gpu    (usa a placa NVIDIA, download de ~2,5 GB)
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1
if not exist .venv\Scripts\activate.bat (
  echo Rode primeiro o instalar.bat
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
if /i "%1"=="gpu" (
  pip install torch --index-url https://download.pytorch.org/whl/cu126 || (echo Falha ao instalar o PyTorch com GPU. & pause & exit /b 1)
) else (
  pip install torch || (echo Falha ao instalar o PyTorch. & pause & exit /b 1)
)
pip install -e .[ucraniano] || (echo Falha ao instalar dependencias. & pause & exit /b 1)
python -m bridge_poc.modelos parakeet-uk || (echo Falha ao baixar o modelo. & pause & exit /b 1)
echo.
echo Pronto. O iniciar.bat passa a usar o Parakeet UK para o ucraniano automaticamente.
pause
