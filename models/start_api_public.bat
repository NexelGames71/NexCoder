@echo off
title NexCoder Model API (network-exposed)
echo ============================================
echo   NexCoder Model API - network mode
echo   Binds 0.0.0.0 so other machines/tunnels
echo   can reach it. Set NEXCODER_API_KEY first
echo   if this leaves your trusted network.
echo ============================================
echo.

cd /d "%~dp0"

REM Prefer NexCoder's own venv (its activate.bat points at a stale drive).
set PYTHON=%~dp0..\venv\Scripts\python.exe
if not exist "%PYTHON%" set PYTHON=python

if "%NEXCODER_GGUF_MODEL_PATH%"=="" (
  set MODEL_PATH=%~dp0coder\Qwen3-Coder-30B-A3B-Instruct-GGUF\Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf
) else (
  set MODEL_PATH=%NEXCODER_GGUF_MODEL_PATH%
)

if "%NEXCODER_GGUF_CHAT_FORMAT%"=="" set NEXCODER_GGUF_CHAT_FORMAT=chatml
if "%NEXCODER_GGUF_GPU_LAYERS%"=="" set NEXCODER_GGUF_GPU_LAYERS=10
if "%NEXCODER_GGUF_CTX%"=="" set NEXCODER_GGUF_CTX=32768
if "%NEXCODER_GGUF_KV_OFFLOAD%"=="" set NEXCODER_GGUF_KV_OFFLOAD=0
if "%NEXCODER_GGUF_N_BATCH%"=="" set NEXCODER_GGUF_N_BATCH=1024
if "%NEXCODER_GGUF_CACHE_MB%"=="" set NEXCODER_GGUF_CACHE_MB=2048
set NEXCODER_REQUIRE_GPU=1

echo Your LAN addresses (use one of these + :8002 from another machine):
ipconfig | findstr /C:"IPv4"
echo.
echo Model: %MODEL_PATH%
echo Endpoint (this machine): http://127.0.0.1:8002/v1
echo.

"%PYTHON%" server.py --host 0.0.0.0 --port 8002 --model-path "%MODEL_PATH%"

pause
