@echo off
REM BRIDGE - modo seguro: so os componentes basicos (Whisper + NLLB), como na primeira versao
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1
set KMP_DUPLICATE_LIB_OK=TRUE
call .venv\Scripts\activate.bat
python -m bridge_poc computador --ucraniano whisper --tradutor nllb %*
if errorlevel 1 pause
