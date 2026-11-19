@echo off
REM BRIDGE - modo computador (microfone = voce, som do PC = outra pessoa)
cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1
call .venv\Scripts\activate.bat
python -m bridge_poc computador %*
if errorlevel 1 pause
