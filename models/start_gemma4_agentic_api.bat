@echo off
title NexCoder Gemma4 Agentic Model API
echo ============================================
echo   NexCoder Gemma4-12B v2 Agentic API
echo   Endpoint: http://127.0.0.1:8000
echo ============================================
echo.

cd /d "%~dp0"

if exist C:\nexa\.venv\Scripts\activate.bat (
  call C:\nexa\.venv\Scripts\activate.bat
) else if exist ..\venv\Scripts\activate.bat (
  call ..\venv\Scripts\activate.bat
)

if "%NEXCODER_GGUF_MODEL_PATH%"=="" (
  set MODEL_DIR=C:\NexaModels\gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF\gemma4-v2-Q4_K_M.gguf
) else (
  set MODEL_DIR=%NEXCODER_GGUF_MODEL_PATH%
)

echo Starting server with:
echo %MODEL_DIR%
echo.
python server.py --port 8000 --model-path "%MODEL_DIR%"

pause
