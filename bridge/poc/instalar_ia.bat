@echo off
REM BRIDGE - traducao por IA local (TranslateGemma, Google) via Ollama. Opcional.
cd /d %~dp0
chcp 65001 >nul
set "OLLAMA=ollama"
where ollama >nul 2>nul || (
  echo Instalando o Ollama...
  winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements || (
    echo Nao foi possivel instalar automaticamente. Baixe em https://ollama.com/download e rode este arquivo de novo.
    pause
    exit /b 1
  )
  set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
)
echo Baixando o TranslateGemma 4B (~2,5 GB)...
"%OLLAMA%" pull hf.co/bullerwins/translategemma-4b-it-GGUF:Q4_K_M || (echo Falha ao baixar o modelo. Abra o Ollama e tente de novo. & pause & exit /b 1)
echo.
echo Pronto. Com o Ollama aberto, o iniciar.bat usa a IA para traduzir ucraniano para portugues.
pause
