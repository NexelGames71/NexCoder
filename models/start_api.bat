@echo off
title NexCoder Model API Server
echo ============================================
echo   NexCoder Model API Server
echo   Model: Qwen2.5-Coder-7B-Instruct-GGUF
echo   Endpoint: http://127.0.0.1:8001
echo ============================================
echo.

cd /d "%~dp0"

if exist C:\nexa\.venv\Scripts\activate.bat (
  call C:\nexa\.venv\Scripts\activate.bat
) else if exist ..\venv\Scripts\activate.bat (
  call ..\venv\Scripts\activate.bat
)

if "%NEXCODER_GGUF_MODEL_PATH%"=="" (
  set MODEL_PATH=%~dp0coder\Qwen2.5-Coder-7B-Instruct-GGUF\qwen2.5-coder-7b-instruct-q6_k.gguf
) else (
  set MODEL_PATH=%NEXCODER_GGUF_MODEL_PATH%
)

if "%NEXCODER_GGUF_CHAT_FORMAT%"=="" (
  set NEXCODER_GGUF_CHAT_FORMAT=chatml
)

echo Starting server...
echo %MODEL_PATH%
set NEXCODER_REQUIRE_GPU=1
set NEXCODER_GGUF_GPU_LAYERS=-1
python server.py --port 8001 --model-path "%MODEL_PATH%"

pause
