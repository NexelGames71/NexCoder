"""ModelConnector - OpenAI-compatible chat completions client for Nexa AI."""

import json
import logging
import os
import time
from typing import Any, Generator

import httpx

from nexcoder.agent.errors import (
    AgentCancelledError, ModelHTTPError, ModelStreamError, ModelUnavailableError,
)

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_WINDOW = 8192
DEFAULT_MAX_OUTPUT_TOKENS = 3072
DEFAULT_CONTEXT_RESERVE = 384


SYSTEM_PROMPTS = {
    "ask": (
        "You are NexCoder AI, an expert coding assistant. "
        "Answer questions about code clearly and concisely. "
        "Use code blocks with language identifiers. "
        "Do NOT modify any files - this is a read-only mode."
    ),
    "edit": (
        "You are NexCoder AI, an expert code editor. "
        "Generate precise, minimal code changes. "
        "Wrap code changes in ```diff blocks with file paths. "
        "Show only the changed sections with sufficient context."
    ),
    "agent": (
        "You are NexCoder AI, an autonomous coding agent. "
        "You can read files, plan changes, generate patches, and run commands. "
        "DO NOT answer with free-form chat during intermediate agent steps. "
        "Your intermediate response must contain one or more XML tool call blocks exactly like "
        "<tool_call name=\"tool_name\">{\"path\":\"foo.py\"}</tool_call>, or a final patch response wrapped in ```diff blocks. "
        "When using tools, prefer read_file, search_grep, list_directory, write_file, and run_command. "
        "If you already have a patch ready, emit it directly as diff output. "
        "If your last answer did not include a tool call or diff block, do not repeat prose: instead, correct to only tool calls or diff output."
    ),
    "debug": (
        "You are NexCoder AI, an expert debugger. "
        "Analyze error messages and stack traces. "
        "Identify the root cause and propose targeted fixes. "
        "Show fixes as ```diff blocks."
    ),
    "review": (
        "You are NexCoder AI, a thorough code reviewer. "
        "Analyze code for: security vulnerabilities, bugs, performance issues, "
        "code quality, and architectural concerns. "
        "Provide a structured review with severity levels (Critical, Warning, Info)."
    ),
}


class ModelConnector:
    """Connects to OpenAI-compatible AI backends."""

    def __init__(self) -> None:
        self._base_url = os.getenv("NEXA_API_URL", "http://127.0.0.1:8002")
        self._api_key = os.getenv("NEXA_API_KEY", "")
        self._model = os.getenv("NEXA_MODEL", "default")
        self._timeout = float(os.getenv("NEXA_TIMEOUT", "120"))

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        mode: str = "ask",
        stream: bool = True,
        temperature: float | None = None,
        max_tokens: int = 4096,
        include_system_prompt: bool = True,
        raise_on_error: bool = False,
    ) -> Generator[str, None, None] | str:
        """Send a chat completion request. Yields chunks if streaming."""
        if temperature is None:
            temperature = 0.2 if mode in {"agent", "edit", "debug"} else 0.7

        full_messages = list(messages)
        if include_system_prompt and (not messages or messages[0].get("role") != "system"):
            system_prompt = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["ask"])
            full_messages = [{"role": "system", "content": system_prompt}] + messages

        context_window = max(2048, int(os.getenv("NEXA_CONTEXT_WINDOW", str(DEFAULT_CONTEXT_WINDOW))))
        output_cap = max(256, int(os.getenv("NEXA_MAX_OUTPUT_TOKENS", str(DEFAULT_MAX_OUTPUT_TOKENS))))
        reserve = max(128, int(os.getenv("NEXA_CONTEXT_RESERVE", str(DEFAULT_CONTEXT_RESERVE))))
        max_tokens = min(max_tokens, output_cap, context_window - reserve - 256)
        full_messages = self._fit_messages(full_messages, context_window - max_tokens - reserve)

        payload = {
            "model": self._model,
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        url = f"{self._base_url.rstrip('/')}/v1/chat/completions"

        if stream:
            return self._stream_request(url, payload, headers, raise_on_error=raise_on_error)
        return self._sync_request(url, payload, headers, raise_on_error=raise_on_error)

    @staticmethod
    def _estimated_tokens(text: str) -> int:
        """Conservatively estimate Qwen/code tokens without a tokenizer dependency."""
        return max(1, (len(text or "") + 2) // 3)

    @classmethod
    def _fit_messages(
        cls,
        messages: list[dict[str, str]],
        input_budget: int,
    ) -> list[dict[str, str]]:
        """Keep system and newest turns inside the model input budget.

        Tool observations and the latest contract are retained first. Older
        chat/project context is dropped or truncated, matching the compaction
        boundary used by production coding agents instead of letting the
        backend terminate an oversized stream.
        """
        budget = max(256, int(input_budget))
        if not messages:
            return []

        normalized = [
            {"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")}
            for item in messages
        ]
        total = sum(cls._estimated_tokens(item["content"]) + 6 for item in normalized)
        if total <= budget:
            return normalized

        system = normalized[0] if normalized[0]["role"] == "system" else None
        remaining = budget
        kept: list[tuple[int, dict[str, str]]] = []

        if system is not None:
            system_tokens = cls._estimated_tokens(system["content"]) + 6
            system_cap = min(system_tokens, max(128, budget // 4))
            content = cls._truncate_content(system["content"], system_cap - 6, keep_tail=False)
            kept.append((0, {**system, "content": content}))
            remaining -= cls._estimated_tokens(content) + 6

        start = 1 if system is not None else 0
        for index in range(len(normalized) - 1, start - 1, -1):
            item = normalized[index]
            cost = cls._estimated_tokens(item["content"]) + 6
            if cost <= remaining:
                kept.append((index, item))
                remaining -= cost
                continue
            if remaining >= 160:
                content = cls._truncate_content(item["content"], remaining - 6, keep_tail=index == len(normalized) - 1)
                kept.append((index, {**item, "content": content}))
                remaining -= cls._estimated_tokens(content) + 6
            if remaining < 64:
                break

        return [item for _, item in sorted(kept, key=lambda pair: pair[0])]

    @classmethod
    def _truncate_content(cls, content: str, token_budget: int, *, keep_tail: bool) -> str:
        marker = "\n[... older context compacted ...]\n"
        char_budget = max(0, token_budget * 3 - len(marker))
        if len(content) <= char_budget:
            return content
        if char_budget == 0:
            return marker.strip()
        if keep_tail:
            return marker + content[-char_budget:]
        return content[:char_budget] + marker

    def _stream_request(
        self,
        url: str,
        payload: dict,
        headers: dict,
        *,
        raise_on_error: bool = False,
    ) -> Generator[str, None, None]:
        """Make a streaming SSE request and yield text chunks."""
        try:
            with httpx.Client(timeout=self._timeout) as client:
                with client.stream("POST", url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
        except httpx.ConnectError as exc:
            if raise_on_error:
                raise ModelUnavailableError(
                    f"Cannot connect to AI backend at {self._base_url}"
                ) from exc
            yield (
                "\n\nWarning: Cannot connect to AI backend. "
                f"Make sure the Nexa server is running at {self._base_url}"
            )
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                detail = str(exc.response.json().get("detail") or "")
            except Exception:
                pass
            message = f"AI backend error: HTTP {exc.response.status_code}"
            if detail:
                message = f"{message}: {detail}"
            if raise_on_error:
                raise ModelHTTPError(message) from exc
            yield f"\n\nWarning: {message}"
        except Exception as exc:
            logger.error("Model connector error: %s", exc)
            if raise_on_error:
                raise ModelStreamError(f"AI stream interrupted: {exc}") from exc
            yield f"\n\nWarning: {exc}"

    def _sync_request(
        self,
        url: str,
        payload: dict,
        headers: dict,
        *,
        raise_on_error: bool = False,
    ) -> str:
        """Make a synchronous request."""
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except httpx.ConnectError as exc:
            if raise_on_error:
                raise ModelUnavailableError("Cannot connect to AI backend.") from exc
            return "Warning: Cannot connect to AI backend. Make sure the Nexa server is running."
        except httpx.HTTPStatusError as exc:
            if raise_on_error:
                raise ModelHTTPError(f"AI backend error: HTTP {exc.response.status_code}") from exc
            return f"Warning: AI backend error: {exc.response.status_code}"
        except Exception as exc:
            logger.error("Model connector sync error: %s", exc)
            if raise_on_error:
                raise ModelStreamError(f"AI request failed: {exc}") from exc
            return f"Warning: {exc}"

    @staticmethod
    def merge_stream_chunks(chunks: list[dict]) -> dict:
        """Aggregate OpenAI streaming chunks into one assistant message."""
        content_parts: list[str] = []
        calls: dict[int, dict] = {}
        usage: dict | None = None
        for item in chunks:
            if isinstance(item.get("usage"), dict):
                usage = item["usage"]
            delta = (item.get("choices") or [{}])[0].get("delta") or {}
            if delta.get("content"):
                content_parts.append(str(delta["content"]))
            for fragment in delta.get("tool_calls") or []:
                index = int(fragment.get("index", 0))
                slot = calls.setdefault(index, {
                    "id": "", "type": "function",
                    "function": {"name": "", "arguments": ""}})
                if fragment.get("id"):
                    slot["id"] = fragment["id"]
                fn = fragment.get("function") or {}
                if fn.get("name"):
                    slot["function"]["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["function"]["arguments"] += fn["arguments"]
        message: dict = {"role": "assistant", "content": "".join(content_parts)}
        if calls:
            message["tool_calls"] = [calls[i] for i in sorted(calls)]
        if usage:
            # Real token counts from the backend; the conversation uses
            # them to calibrate its estimator. Underscore keys never
            # travel back to the API.
            message["_usage"] = usage
        return message

    # Local single-slot servers return 429 while another request runs.
    # The agent path queues politely instead of failing the whole run.
    BUSY_RETRY_SECONDS = 10.0
    BUSY_RETRY_LIMIT = 90  # up to 15 minutes of queueing
    # Prompt processing on big local models can be silent for minutes
    # before the first SSE byte; the read timeout must survive that.
    AGENT_READ_TIMEOUT = 900.0

    def chat_agent(
        self,
        messages: list[dict],
        *,
        extras: dict | None = None,
        on_delta=None,
        temperature: float = 0.2,
        max_tokens: int = 3072,
    ) -> dict:
        """Agent-loop entry point: full assistant message, exceptions on failure."""
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            # Ask the backend to append a final usage chunk with the real
            # prompt/completion token counts. The conversation uses it to
            # calibrate its chars/3 estimator so the context meter and
            # compaction track the actual tokenizer, not a guess.
            "stream_options": {"include_usage": True},
        }
        payload.update(extras or {})
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        url = f"{self._base_url.rstrip('/')}/v1/chat/completions"
        timeout = httpx.Timeout(
            connect=10.0, read=self.AGENT_READ_TIMEOUT, write=60.0, pool=30.0)
        attempts = 0
        while True:
            chunks: list[dict] = []
            try:
                with httpx.Client(timeout=timeout) as client:
                    with client.stream("POST", url, json=payload, headers=headers) as response:
                        response.raise_for_status()
                        for line in response.iter_lines():
                            if not line or not line.startswith("data: "):
                                continue
                            data = line[6:]
                            if data.strip() == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            chunks.append(chunk)
                            if on_delta:
                                delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                                if delta.get("content"):
                                    on_delta(str(delta["content"]))
            except httpx.ConnectError as exc:
                raise ModelUnavailableError(
                    f"Cannot connect to AI backend at {self._base_url}") from exc
            except httpx.HTTPStatusError as exc:
                if (exc.response.status_code == 429
                        and attempts < self.BUSY_RETRY_LIMIT):
                    attempts += 1
                    logger.info("Model busy (429); retry %d in %.0fs",
                                attempts, self.BUSY_RETRY_SECONDS)
                    time.sleep(self.BUSY_RETRY_SECONDS)
                    continue
                detail = ""
                try:
                    exc.response.read()
                    detail = f": {exc.response.text[:300]}"
                except Exception:
                    pass
                raise ModelHTTPError(
                    f"AI backend error: HTTP {exc.response.status_code}{detail}") from exc
            except AgentCancelledError:
                raise  # user cancel must not be masked as a stream error
            except Exception as exc:
                raise ModelStreamError(f"AI stream interrupted: {exc}") from exc
            return self.merge_stream_chunks(chunks)

    def set_endpoint(self, url: str) -> None:
        """Update the AI endpoint URL."""
        self._base_url = url

    def set_model(self, model: str) -> None:
        """Update the model name."""
        self._model = model

    def set_api_key(self, key: str) -> None:
        """Update the API key."""
        self._api_key = key

    def test_connection(self) -> dict[str, Any]:
        """Test the connection to the AI backend."""
        try:
            with httpx.Client(timeout=10) as client:
                url = f"{self._base_url.rstrip('/')}/v1/models"
                headers = {}
                if self._api_key:
                    headers["Authorization"] = f"Bearer {self._api_key}"

                response = client.get(url, headers=headers)
                if response.status_code == 200:
                    return {"connected": True, "models": response.json()}
                return {"connected": False, "error": f"HTTP {response.status_code}"}
        except Exception as exc:
            return {"connected": False, "error": str(exc)}


class AgentModelClient:
    """Adapts ModelConnector to the AgentLoop ModelClient protocol."""

    def __init__(self, connector: ModelConnector) -> None:
        self.connector = connector

    def complete(self, messages, *, extras, on_delta=None):
        return self.connector.chat_agent(messages, extras=extras, on_delta=on_delta)
