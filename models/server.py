"""
NexCoder Model API Server
=========================
A lightweight OpenAI-compatible API server that serves local coding models.
It supports:
- Transformers/GPTQ model directories, used by the bundled Qwen preset.
- GGUF model files through llama-cpp-python, used by lightweight local agents.

Exposes:
  POST /v1/chat/completions   (streaming + non-streaming)
  GET  /v1/models

Start with:
  python server.py
  # or: python server.py --port 8001 --model-path ./coder/Qwen2.5-Coder-7B-Instruct-GGUF/qwen2.5-coder-7b-instruct-q6_k.gguf
"""

import argparse
import asyncio
import difflib
import hashlib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

import torch
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer
from queue import Empty, Queue
from threading import Event, Lock, Thread

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nexcoder-api")

# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(title="NexCoder Model API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional bearer-token auth. Set NEXCODER_API_KEY to require it before
# exposing the server beyond localhost. Empty = open (fine on 127.0.0.1).
REQUIRED_API_KEY = os.getenv("NEXCODER_API_KEY", "").strip()


def require_api_key(authorization: str = Header(default="")) -> None:
    """Enforce ``Authorization: Bearer <key>`` when a key is configured."""
    if not REQUIRED_API_KEY:
        return
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if token != REQUIRED_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

# ── Global State ──────────────────────────────────────────────────────────────
model = None
tokenizer = None
MODEL_NAME = "default"
MODEL_KIND = "transformers"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
INFERENCE_BACKEND = DEVICE
GPU_OFFLOAD_AVAILABLE = torch.cuda.is_available()
LLAMA_INFERENCE_LOCK = Lock()


# ── Request / Response Schemas ────────────────────────────────────────────────
def _coerce_content(value: Any) -> str:
    """Normalize OpenAI message content to a plain string.

    Third-party clients (Cursor, Continue, aider) send ``content`` as a
    list of parts like ``[{"type": "text", "text": "..."}]`` or, rarely,
    ``None``. Flatten any of these to text so the model sees a string.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(value)


class ChatMessage(BaseModel):
    model_config = {"extra": "ignore"}
    role: str = "user"
    content: Any = ""


class ChatCompletionRequest(BaseModel):
    # Ignore the extra sampling fields OpenAI clients send (presence_penalty,
    # frequency_penalty, tools, response_format, ...) instead of 422-ing.
    model_config = {"extra": "ignore"}
    model: str = "default"
    messages: list[ChatMessage]
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=4096)
    stream: bool = False
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    stop: list[str] | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/v1/models")
async def list_models(_auth: None = Depends(require_api_key)):
    """List available models (OpenAI-compatible)."""
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_NAME,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "nexcoder-local",
            }
        ],
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "model_kind": MODEL_KIND,
        "device": DEVICE,
        "inference_backend": INFERENCE_BACKEND,
        "gpu_offload_available": GPU_OFFLOAD_AVAILABLE,
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "busy": LLAMA_INFERENCE_LOCK.locked() if MODEL_KIND == "gguf" else False,
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest,
                           _auth: None = Depends(require_api_key)):
    """OpenAI-compatible chat completions endpoint."""
    global model, tokenizer

    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    if tokenizer is None and MODEL_KIND != "gguf":
        raise HTTPException(status_code=503, detail="Tokenizer not loaded yet")

    messages = [{"role": m.role, "content": _coerce_content(m.content)}
                for m in request.messages]
    if request.max_tokens is None:
        request.max_tokens = 4096
    if MODEL_KIND == "gguf":
        return await _llama_chat_completions(request, messages)

    # Build the chat prompt using the tokenizer's chat template

    try:
        input_text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        # Fallback: manual prompt assembly if chat template fails
        parts = []
        for m in messages:
            if m["role"] == "system":
                parts.append(f"<|im_start|>system\n{m['content']}<|im_end|>")
            elif m["role"] == "user":
                parts.append(f"<|im_start|>user\n{m['content']}<|im_end|>")
            elif m["role"] == "assistant":
                parts.append(f"<|im_start|>assistant\n{m['content']}<|im_end|>")
        parts.append("<|im_start|>assistant\n")
        input_text = "\n".join(parts)

    input_ids = tokenizer(input_text, return_tensors="pt").input_ids.to(DEVICE)

    generation_kwargs = {
        "input_ids": input_ids,
        "max_new_tokens": request.max_tokens,
        "temperature": max(request.temperature, 0.01),  # avoid 0
        "top_p": request.top_p,
        "do_sample": request.temperature > 0.01,
        "pad_token_id": tokenizer.eos_token_id,
    }

    request_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    if request.stream:
        return StreamingResponse(
            _stream_response(generation_kwargs, request_id, request.model),
            media_type="text/event-stream",
        )
    else:
        return _sync_response(generation_kwargs, request_id, request.model, input_ids)


def _sync_response(generation_kwargs: dict, request_id: str, model_name: str, input_ids):
    """Generate a complete (non-streaming) response."""
    with torch.no_grad():
        output_ids = model.generate(**generation_kwargs)

    # Slice off the input prompt tokens
    new_tokens = output_ids[0][input_ids.shape[1] :]
    response_text = tokenizer.decode(new_tokens, skip_special_tokens=True)

    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": input_ids.shape[1],
            "completion_tokens": len(new_tokens),
            "total_tokens": input_ids.shape[1] + len(new_tokens),
        },
    }


async def _stream_response(
    generation_kwargs: dict, request_id: str, model_name: str
) -> AsyncGenerator[str, None]:
    """Stream SSE chunks matching the OpenAI streaming format."""
    streamer = TextIteratorStreamer(tokenizer, skip_special_tokens=True, skip_prompt=True)
    generation_kwargs["streamer"] = streamer

    # Run generation in a background thread so we can stream tokens
    thread = Thread(target=_generate_threaded, args=(generation_kwargs,))
    thread.start()

    while True:
        # Check if queue has items to avoid blocking next(streamer)
        if not streamer.text_queue.empty():
            try:
                text_chunk = next(streamer)
                if not text_chunk:
                    continue
                chunk_data = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_name,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": text_chunk},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk_data)}\n\n"
            except StopIteration:
                break
        else:
            # Yield control to the async event loop
            await asyncio.sleep(0.005)

    # Send the final [DONE] marker
    final_chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_name,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"

    thread.join()


def _generate_threaded(kwargs: dict):
    """Run model.generate in a thread (for streaming)."""
    with torch.no_grad():
        model.generate(**kwargs)


class SemanticResponseCache:
    """Response cache for single-turn questions keyed by near-identical text.

    Deliberately NOT used for multi-turn or tool-bearing requests: in agent
    runs, similar wording does not imply similar project state, and replaying
    a cached tool call against changed files would be wrong.
    """

    def __init__(self, max_entries: int = 64, ttl_seconds: float = 1800.0,
                 threshold: float = 0.96) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.threshold = threshold
        self._entries: list[dict] = []
        self._lock = Lock()

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.lower().split())

    @staticmethod
    def eligibility_key(request, messages: list[dict]):
        """Return (system_hash, user_text) for cacheable requests, else None."""
        if getattr(request, "tools", None):
            return None
        non_system = [m for m in messages if m.get("role") != "system"]
        if len(non_system) != 1 or non_system[0].get("role") != "user":
            return None
        user_text = str(non_system[0].get("content") or "")
        if not user_text.strip() or "<tool_response>" in user_text:
            return None
        system_text = "\n".join(
            str(m.get("content") or "") for m in messages if m.get("role") == "system")
        system_hash = hashlib.sha256(system_text.encode("utf-8")).hexdigest()[:16]
        return system_hash, user_text

    def lookup(self, key) -> str | None:
        system_hash, user_text = key
        norm = self._normalize(user_text)
        now = time.time()
        with self._lock:
            self._entries = [e for e in self._entries if now - e["ts"] < self.ttl_seconds]
            for entry in reversed(self._entries):
                if entry["system_hash"] != system_hash:
                    continue
                ratio = difflib.SequenceMatcher(None, norm, entry["norm"]).ratio()
                if ratio >= self.threshold:
                    return entry["content"]
        return None

    def store(self, key, content: str) -> None:
        if not content.strip():
            return
        system_hash, user_text = key
        with self._lock:
            self._entries.append({
                "system_hash": system_hash,
                "norm": self._normalize(user_text),
                "content": content,
                "ts": time.time(),
            })
            if len(self._entries) > self.max_entries:
                self._entries = self._entries[-self.max_entries:]


SEMANTIC_CACHE: SemanticResponseCache | None = None


async def _semantic_cache_stream(content: str, request_id: str, model_name: str):
    """Replay a cached answer in the normal SSE shape."""
    chunk = {
        "id": request_id, "object": "chat.completion.chunk",
        "created": int(time.time()), "model": model_name,
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(chunk)}\n\n"
    final = {
        "id": request_id, "object": "chat.completion.chunk",
        "created": int(time.time()), "model": model_name,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final)}\n\n"
    yield "data: [DONE]\n\n"


async def _llama_chat_completions(request: ChatCompletionRequest, messages: list[dict]):
    """Handle chat completions for llama-cpp GGUF models."""
    cache_key = None
    if SEMANTIC_CACHE is not None:
        cache_key = SemanticResponseCache.eligibility_key(request, messages)
        if cache_key is not None:
            cached = SEMANTIC_CACHE.lookup(cache_key)
            if cached is not None:
                logger.info("Semantic cache hit")
                cached_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
                if request.stream:
                    return StreamingResponse(
                        _semantic_cache_stream(cached, cached_id, request.model),
                        media_type="text/event-stream")
                return {
                    "id": cached_id, "object": "chat.completion",
                    "created": int(time.time()), "model": request.model,
                    "choices": [{"index": 0,
                                 "message": {"role": "assistant", "content": cached},
                                 "finish_reason": "stop"}],
                    "usage": {"cached": True},
                }
    if not LLAMA_INFERENCE_LOCK.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="The local model is already processing another request. Wait for it to finish or cancel it.",
        )
    request_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    llama_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

    kwargs = {
        "messages": llama_messages,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_tokens": request.max_tokens,
        "stream": request.stream,
    }
    if request.stop:
        kwargs["stop"] = request.stop

    if request.stream:
        return StreamingResponse(
            _llama_stream_response(kwargs, request_id, request.model, cache_key=cache_key),
            media_type="text/event-stream",
        )

    try:
        completion = await asyncio.to_thread(_llama_completion, kwargs)
    except Exception as exc:
        logger.exception("GGUF chat completion failed")
        raise HTTPException(status_code=500, detail=f"GGUF chat completion failed: {exc}") from exc
    content = completion.get("choices", [{}])[0].get("message", {}).get("content", "")
    if cache_key is not None and SEMANTIC_CACHE is not None:
        SEMANTIC_CACHE.store(cache_key, content)
    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": completion.get("choices", [{}])[0].get("finish_reason", "stop"),
            }
        ],
        "usage": completion.get("usage", {}),
    }


async def _llama_stream_response(kwargs: dict, request_id: str, model_name: str,
                                 cache_key=None) -> AsyncGenerator[str, None]:
    """Stream llama-cpp chunks in OpenAI-compatible SSE format."""
    output: Queue = Queue()
    finished = object()
    cancelled = Event()
    collected: list[str] = []

    usage_box: dict = {}

    def generate() -> None:
        try:
            for chunk in model.create_chat_completion(**kwargs):
                if cancelled.is_set():
                    break
                output.put(("chunk", chunk))
            # After generation the llama context holds prompt+completion
            # tokens — the exact numbers the client needs to calibrate
            # its context meter. Safe under the single-inference lock.
            try:
                usage_box["total_tokens"] = int(getattr(model, "n_tokens", 0))
            except Exception:
                pass
        except Exception as exc:  # propagated to the async response below
            output.put(("error", exc))
        finally:
            LLAMA_INFERENCE_LOCK.release()
            output.put(("done", finished))

    worker = Thread(target=generate, daemon=True, name="nexcoder-gguf-inference")
    worker.start()
    try:
        while True:
            try:
                kind, value = output.get_nowait()
            except Empty:
                # SSE comments keep proxies and clients alive without adding
                # model text to the agent response.
                yield ": inference-active\n\n"
                await asyncio.sleep(1)
                continue
            if kind == "done":
                break
            if kind == "error":
                raise value
            chunk = value
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content", "")
            if content:
                collected.append(content)
                chunk_data = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_name,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": content},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk_data)}\n\n"
            await asyncio.sleep(0)
    except Exception as exc:
        logger.exception("GGUF streaming completion failed")
        error_chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": f"\n\nError: GGUF streaming completion failed: {exc}"},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
    finally:
        cancelled.set()

    if cache_key is not None and SEMANTIC_CACHE is not None and collected:
        SEMANTIC_CACHE.store(cache_key, "".join(collected))

    final_chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_name,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    total_tokens = int(usage_box.get("total_tokens") or 0)
    if total_tokens > 0:
        # One streamed content chunk ≈ one generated token.
        completion_tokens = len(collected)
        final_chunk["usage"] = {
            "prompt_tokens": max(0, total_tokens - completion_tokens),
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"


def _llama_completion(kwargs: dict):
    try:
        return model.create_chat_completion(**kwargs)
    finally:
        LLAMA_INFERENCE_LOCK.release()


# ── Model Loading ─────────────────────────────────────────────────────────────
def _resolve_model_path(model_path: str) -> str:
    """Resolve a model path, requiring explicit selection for multi-GGUF dirs."""
    abs_path = os.path.abspath(model_path)
    if os.path.isdir(abs_path):
        ggufs = [
            os.path.join(abs_path, name)
            for name in os.listdir(abs_path)
            if name.lower().endswith(".gguf")
        ]
        if len(ggufs) == 1:
            return ggufs[0]
        if len(ggufs) > 1:
            choices = "\n".join(f"  - {path}" for path in sorted(ggufs))
            raise ValueError(
                "Multiple GGUF files found. Pass --model-path to one exact file:\n"
                f"{choices}"
            )
    return abs_path


def load_model(model_path: str):
    """Load a Transformers model directory or GGUF model file."""
    global model, tokenizer, MODEL_NAME, MODEL_KIND, DEVICE, INFERENCE_BACKEND, GPU_OFFLOAD_AVAILABLE

    model_path = _resolve_model_path(model_path)

    if model_path.lower().endswith(".gguf"):
        try:
            import llama_cpp
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError(
                "GGUF support requires llama-cpp-python. Install it in the model server environment."
            ) from exc

        n_ctx = int(os.getenv("NEXCODER_GGUF_CTX", "8192"))
        n_gpu_layers = int(os.getenv("NEXCODER_GGUF_GPU_LAYERS", "-1"))
        threads = int(os.getenv("NEXCODER_GGUF_THREADS", str(max(os.cpu_count() or 4, 4))))
        GPU_OFFLOAD_AVAILABLE = bool(llama_cpp.llama_supports_gpu_offload())
        library_dir = Path(llama_cpp.__file__).resolve().parent / "lib"
        if (library_dir / "ggml-cuda.dll").exists():
            INFERENCE_BACKEND = "cuda"
        elif (library_dir / "ggml-vulkan.dll").exists():
            INFERENCE_BACKEND = "vulkan"
        else:
            INFERENCE_BACKEND = "cpu"
        require_gpu = os.getenv("NEXCODER_REQUIRE_GPU", "0").strip().lower() in {
            "1", "true", "yes", "on",
        }
        if require_gpu and (not GPU_OFFLOAD_AVAILABLE or INFERENCE_BACKEND == "cpu"):
            raise RuntimeError(
                "GPU inference was required, but llama-cpp-python has no GPU backend. "
                "Install requirements-gpu.txt and restart the server."
            )
        DEVICE = f"gpu:{INFERENCE_BACKEND}" if n_gpu_layers != 0 and GPU_OFFLOAD_AVAILABLE else "cpu"
        logger.info(f"Loading GGUF model from: {model_path}")
        logger.info(
            "GGUF backend=%s, gpu_offload=%s, n_gpu_layers=%s",
            INFERENCE_BACKEND,
            GPU_OFFLOAD_AVAILABLE,
            n_gpu_layers,
        )
        # Keep the KV cache in system RAM by default (offload_kqv=False).
        # At large context the KV cache is the biggest VRAM consumer; on an
        # 8GB card a 32k cache overflows. Housing it in the (much larger)
        # system RAM lets us keep both a big context and GPU weight offload.
        # Set NEXCODER_GGUF_KV_OFFLOAD=1 to put it back on the GPU.
        offload_kqv = os.getenv("NEXCODER_GGUF_KV_OFFLOAD", "0").strip().lower() in {
            "1", "true", "yes", "on"}
        llama_kwargs: dict = dict(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_threads=threads,
            chat_format=os.getenv("NEXCODER_GGUF_CHAT_FORMAT", "chatml"),
            verbose=False,
            offload_kqv=offload_kqv,
            # Larger batch = faster prompt processing (agent prompts are long).
            n_batch=int(os.getenv("NEXCODER_GGUF_N_BATCH", "1024")),
        )
        if os.getenv("NEXCODER_GGUF_FLASH_ATTN", "0").strip().lower() in {"1", "true", "yes", "on"}:
            llama_kwargs["flash_attn"] = True
        logger.info("GGUF kv_offload=%s, n_ctx=%s, n_batch=%s",
                    offload_kqv, n_ctx, llama_kwargs["n_batch"])

        def _new_llama(kwargs: dict):
            # Retry with progressively smaller footprints on OOM so the
            # server starts rather than crashing on constrained hardware.
            attempts = [kwargs]
            half = {**kwargs, "n_ctx": max(8192, n_ctx // 2)}
            attempts.append(half)
            for i, attempt in enumerate(attempts):
                try:
                    return Llama(**attempt)
                except TypeError:
                    attempt.pop("flash_attn", None)
                    attempt.pop("n_batch", None)
                    attempt.pop("offload_kqv", None)
                    return Llama(**attempt)
                except (ValueError, RuntimeError, MemoryError) as exc:
                    if i == len(attempts) - 1:
                        raise
                    logger.warning("Model load failed (%s); retrying with "
                                   "n_ctx=%s", exc, attempts[i + 1]["n_ctx"])
            raise RuntimeError("unreachable")

        model = _new_llama(llama_kwargs)

        # Prompt cache: agent loops resend the same growing prefix every
        # turn (system prompt + repo map + history). Caching evaluated
        # prefixes means each turn only processes the new suffix — the
        # difference between minutes and seconds per turn on big models.
        global SEMANTIC_CACHE
        if os.getenv("NEXCODER_SEMANTIC_CACHE", "1").strip().lower() in {"1", "true", "yes", "on"}:
            SEMANTIC_CACHE = SemanticResponseCache(
                threshold=float(os.getenv("NEXCODER_SEMANTIC_CACHE_THRESHOLD", "0.96")),
                ttl_seconds=float(os.getenv("NEXCODER_SEMANTIC_CACHE_TTL", "1800")))
            logger.info("Semantic response cache enabled (single-turn requests)")

        cache_mb = int(os.getenv("NEXCODER_GGUF_CACHE_MB", "2048"))
        if cache_mb > 0:
            try:
                model.set_cache(llama_cpp.LlamaRAMCache(capacity_bytes=cache_mb * 1024 * 1024))
                logger.info("Prompt cache enabled: %d MB RAM", cache_mb)
            except Exception as exc:
                logger.warning("Prompt cache unavailable: %s", exc)
        tokenizer = None
        MODEL_KIND = "gguf"
        MODEL_NAME = os.path.basename(model_path)
        logger.info(f"GGUF model loaded: {MODEL_NAME}")
        return

    logger.info(f"Loading tokenizer from: {model_path}")
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

    logger.info(f"Loading GPTQ model from: {model_path} → device={DEVICE}")
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        device_map="auto",
        torch_dtype=torch.float16,
        trust_remote_code=True,
    )
    model.eval()

    MODEL_KIND = "transformers"
    MODEL_NAME = os.path.basename(model_path)
    logger.info(f"✅ Model loaded: {MODEL_NAME} on {DEVICE}")
    if torch.cuda.is_available():
        mem = torch.cuda.memory_allocated() / 1024**2
        logger.info(f"   GPU memory used: {mem:.0f} MB")


# ── Entry Point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="NexCoder Model API Server")
    parser.add_argument(
        "--model-path",
        type=str,
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "coder",
            "Qwen2.5-Coder-7B-Instruct-GGUF",
            "qwen2.5-coder-7b-instruct-q6_k.gguf",
        ),
        help="Path to a Transformers/GPTQ model directory or exact GGUF model file",
    )
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    load_model(args.model_path)
    logger.info(f"Starting API server on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
