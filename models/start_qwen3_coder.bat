@echo off
title NexCoder Model API Server (Qwen3-Coder-30B-A3B)
echo ============================================
echo   NexCoder Model API Server
echo   Model: Qwen3-Coder-30B-A3B-Instruct Q4_K_M
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
  set MODEL_PATH=%~dp0coder\Qwen3-Coder-30B-A3B-Instruct-GGUF\Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf
) else (
  set MODEL_PATH=%NEXCODER_GGUF_MODEL_PATH%
)

if "%NEXCODER_GGUF_CHAT_FORMAT%"=="" (
  set NEXCODER_GGUF_CHAT_FORMAT=chatml
)

REM 30B MoE (3B active) with an 8GB card: offload what fits, rest on CPU.
REM Raise GPU_LAYERS if you have VRAM headroom; lower it on OOM.
if "%NEXCODER_GGUF_GPU_LAYERS%"=="" set NEXCODER_GGUF_GPU_LAYERS=14
if "%NEXCODER_GGUF_CTX%"=="" set NEXCODER_GGUF_CTX=16384
set NEXCODER_REQUIRE_GPU=1

echo Starting server...
echo %MODEL_PATH%
python server.py --port 8001 --model-path "%MODEL_PATH%"

pause
