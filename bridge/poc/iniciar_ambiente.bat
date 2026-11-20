@echo off
REM BRIDGE - modo ambiente (um microfone ouve os dois)
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1
set KMP_DUPLICATE_LIB_OK=TRUE
call .venv\Scripts\activate.bat
python -m bridge_poc ambiente %*
if errorlevel 1 pause
