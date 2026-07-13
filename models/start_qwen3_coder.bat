@echo off
title NexCoder Model API Server (Qwen3-Coder-30B-A3B)
echo ============================================
echo   NexCoder Model API Server
echo   Model: Qwen3-Coder-30B-A3B-Instruct Q4_K_M
echo   Endpoint: http://127.0.0.1:8002
echo ============================================
echo.

cd /d "%~dp0"

REM Call the venv interpreter directly. Do NOT use activate.bat: this venv
REM was created on another drive and its activation scripts still point
REM there, silently switching to a stale CPU-only environment.
set PYTHON=%~dp0..\venv\Scripts\python.exe
if not exist "%PYTHON%" set PYTHON=python

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
if "%NEXCODER_GGUF_GPU_LAYERS%"=="" set NEXCODER_GGUF_GPU_LAYERS=12
REM 32k context: ~3GB KV cache, fits alongside the ~18GB weights on 32GB
REM RAM. Push to 65536 if you have RAM headroom; lower on OOM at load.
if "%NEXCODER_GGUF_CTX%"=="" set NEXCODER_GGUF_CTX=32768
REM Speed: bigger prompt batches + RAM prompt-cache (turn N only evaluates
REM the new suffix instead of the whole history).
if "%NEXCODER_GGUF_N_BATCH%"=="" set NEXCODER_GGUF_N_BATCH=1024
if "%NEXCODER_GGUF_CACHE_MB%"=="" set NEXCODER_GGUF_CACHE_MB=2048
set NEXCODER_REQUIRE_GPU=1

echo Starting server...
echo %MODEL_PATH%
"%PYTHON%" server.py --port 8002 --model-path "%MODEL_PATH%"

pause
