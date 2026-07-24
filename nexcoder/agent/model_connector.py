"""ModelConnector - OpenAI-compatible chat completions client for Nexa AI."""

import json
import logging
import os
import re
import threading
import time
from typing import Any, Generator
from urllib.parse import urlparse

import httpx

from nexcoder.agent.errors import (
    AgentCancelledError, ModelHTTPError, ModelStreamError, ModelUnavailableError,
)

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_WINDOW = 8192
DEFAULT_MAX_OUTPUT_TOKENS = 3072
DEFAULT_CONTEXT_RESERVE = 384

_THINK_BLOCK_RE = re.compile(
    r"<think\b[^>]*>[\s\S]*?</think\s*>", re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think\b[^>]*>", re.IGNORECASE)
_THINK_CLOSE_RE = re.compile(r"</think\s*>", re.IGNORECASE)


def strip_reasoning_markup(text: str) -> str:
    """Remove provider reasoning wrappers from user-visible model text.

    Some reasoning endpoints return a closing ``</think>`` in ``content``
    even though the opening tag/reasoning channel was consumed upstream.
    In that shape, everything before the orphan closing tag is private
    reasoning and only the suffix is the answer. This function also handles
    normal paired blocks and unfinished opening blocks.
    """
    value = str(text or "")
    previous = None
    while value != previous:
        previous = value
        value = _THINK_BLOCK_RE.sub("", value)
    while True:
        close = _THINK_CLOSE_RE.search(value)
        if close is None:
            break
        # A paired block would already have been removed. A remaining close
        # is orphaned, so its entire prefix is hidden reasoning.
        value = value[close.end():]
    opening = _THINK_OPEN_RE.search(value)
    if opening is not None:
        value = value[:opening.start()]
    value = _THINK_OPEN_RE.sub("", _THINK_CLOSE_RE.sub("", value))
    return value.strip()


def has_image_input(messages: list[dict[str, Any]]) -> bool:
    """Whether an OpenAI-compatible message list contains an image part."""
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        if any(isinstance(part, dict) and part.get("type") in {
            "image_url", "input_image",
        } for part in content):
            return True
    return False


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
        self._base_url = os.getenv(
            "NEXA_API_URL", "https://integrate.api.nvidia.com/v1"
        )
        self._api_key = os.getenv("NEXA_API_KEY", "")
        self._model = os.getenv("NEXA_MODEL", "default")
        self._timeout = float(os.getenv("NEXA_TIMEOUT", "120"))
        self._request_lock = threading.Lock()
        self._active_client: httpx.Client | None = None
        self._active_response: httpx.Response | None = None
        self._cancel_requested = threading.Event()

    @staticmethod
    def _optional_bool_env(name: str) -> bool | None:
        value = os.getenv(name)
        if value is None or not value.strip():
            return None
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        logger.warning("Ignoring invalid boolean value for %s", name)
        return None

    @staticmethod
    def _optional_number_env(
        name: str,
        cast: type[int] | type[float],
    ) -> int | float | None:
        value = os.getenv(name)
        if value is None or not value.strip():
            return None
        try:
            return cast(value)
        except ValueError:
            logger.warning("Ignoring invalid numeric value for %s", name)
            return None

    def _provider_request_extras(self) -> dict[str, Any]:
        """Return optional OpenAI-compatible provider request extensions.

        These knobs stay provider-neutral and opt-in. Backends that do not
        implement reasoning extensions never receive them, while NVIDIA NIM
        and compatible servers can enable thinking without a model-specific
        branch in the agent loop.
        """
        extras: dict[str, Any] = {}
        top_p = self._optional_number_env("NEXCODER_TOP_P", float)
        if top_p is not None:
            extras["top_p"] = min(1.0, max(0.0, float(top_p)))

        scoped_models = {
            model.strip() for model in
            os.getenv("NEXCODER_REASONING_MODELS", "").split(",")
            if model.strip()
        }
        if scoped_models and self._model not in scoped_models:
            return extras

        reasoning_budget = self._optional_number_env(
            "NEXCODER_REASONING_BUDGET", int)
        if reasoning_budget is not None:
            extras["reasoning_budget"] = max(-1, int(reasoning_budget))

        reasoning_effort = os.getenv("NEXCODER_REASONING_EFFORT", "").strip()
        if reasoning_effort:
            extras["reasoning_effort"] = reasoning_effort

        template_options: dict[str, bool] = {}
        for env_name, option_name in (
            ("NEXCODER_ENABLE_THINKING", "enable_thinking"),
            ("NEXCODER_FORCE_NONEMPTY_CONTENT", "force_nonempty_content"),
        ):
            value = self._optional_bool_env(env_name)
            if value is not None:
                template_options[option_name] = value
        if template_options:
            extras["chat_template_kwargs"] = template_options
        return extras

    def cancel_current_request(self) -> None:
        """Abort an in-flight HTTP stream from another thread.

        Cooperative tokens cannot be observed while httpx is blocked waiting
        for response bytes. Closing the response/socket wakes that read so the
        agent worker can finish cancellation immediately.
        """
        self._cancel_requested.set()
        with self._request_lock:
            response = self._active_response
            client = self._active_client
        for resource in (response, client):
            if resource is None:
                continue
            try:
                resource.close()
            except Exception:
                logger.debug("Error while closing cancelled model stream",
                             exc_info=True)

    def _set_active_request(
        self,
        client: httpx.Client | None,
        response: httpx.Response | None = None,
    ) -> None:
        with self._request_lock:
            self._active_client = client
            self._active_response = response

    def _clear_active_request(self, client: httpx.Client) -> None:
        with self._request_lock:
            if self._active_client is client:
                self._active_client = None
                self._active_response = None

    def _raise_if_request_cancelled(self) -> None:
        if self._cancel_requested.is_set():
            raise AgentCancelledError("cancelled by user")

    def _api_url(self, resource: str) -> str:
        """Build an OpenAI-compatible URL from either host or `/v1` base.

        Provider SDK examples commonly use a base such as
        ``https://host/v1`` while NexCoder historically expected only
        ``https://host``. Accept both, plus a copied chat-completions URL,
        without ever producing ``/v1/v1/...``.
        """
        base = self._base_url.rstrip("/")
        if base.endswith("/v1/chat/completions"):
            base = base.removesuffix("/chat/completions")
        elif not base.endswith("/v1"):
            base += "/v1"
        return f"{base}/{resource.lstrip('/')}"

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
        payload.update(self._provider_request_extras())

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        url = self._api_url("chat/completions")

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
        finish_reason: str | None = None
        for item in chunks:
            if isinstance(item.get("usage"), dict):
                usage = item["usage"]
            choice = (item.get("choices") or [{}])[0]
            if choice.get("finish_reason"):
                finish_reason = str(choice["finish_reason"])
            delta = choice.get("delta") or {}
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
        message: dict = {
            "role": "assistant",
            "content": strip_reasoning_markup("".join(content_parts)),
        }
        if calls:
            message["tool_calls"] = [calls[i] for i in sorted(calls)]
        if usage:
            # Real token counts from the backend; the conversation uses
            # them to calibrate its estimator. Underscore keys never
            # travel back to the API.
            message["_usage"] = usage
        if finish_reason:
            message["_finish_reason"] = finish_reason
        return message

    @staticmethod
    def _validate_agent_message(message: dict) -> dict:
        """Reject successful HTTP streams that contain no usable answer.

        Hosted GPU gateways can return an empty/queued body with a 2xx
        status. Treating it as a completed assistant turn silently ends an
        agent or mesh unit with zero output and zero changes. Raising a stream
        error lets AgentLoop use its bounded, cancellable retry path.
        """
        if message.get("content") or message.get("tool_calls"):
            return message
        raise ModelStreamError(
            "AI provider returned an empty completion; retrying the turn")

    # Local single-slot servers return 429 while another request runs, so
    # they can queue for a long time. Hosted APIs use 429 for rate limits or
    # exhausted trial capacity and must fail quickly with a visible error.
    BUSY_RETRY_SECONDS = 10.0
    BUSY_RETRY_LIMIT = 90  # up to 15 minutes of queueing
    CLOUD_RATE_LIMIT_RETRIES = 1
    # Prompt processing on big local models can be silent for minutes
    # before the first SSE byte; the read timeout must survive that.
    AGENT_READ_TIMEOUT = 900.0

    def _rate_limit_retry_limit(self) -> int:
        configured = os.getenv("NEXA_RATE_LIMIT_RETRIES")
        if configured is not None:
            try:
                return max(0, int(configured))
            except ValueError:
                pass
        hostname = (urlparse(self._base_url).hostname or "").lower()
        is_local = hostname in {"localhost", "127.0.0.1", "::1"}
        return (self.BUSY_RETRY_LIMIT if is_local
                else self.CLOUD_RATE_LIMIT_RETRIES)

    @staticmethod
    def _interruptible_sleep(seconds: float, on_delta=None) -> None:
        """Wait between retries while keeping the Stop button responsive."""
        deadline = time.monotonic() + max(0.0, seconds)
        while True:
            if on_delta is not None:
                # AgentLoop's delta callback checks its cancellation token
                # before ignoring this empty progress pulse.
                on_delta("")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.25, remaining))

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
        payload.update(self._provider_request_extras())
        payload.update(extras or {})
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        url = self._api_url("chat/completions")
        timeout = httpx.Timeout(
            connect=10.0, read=self.AGENT_READ_TIMEOUT, write=60.0, pool=30.0)
        attempts = 0
        while True:
            self._raise_if_request_cancelled()
            chunks: list[dict] = []
            client = httpx.Client(timeout=timeout)
            self._set_active_request(client)
            try:
                with client:
                    with client.stream("POST", url, json=payload, headers=headers) as response:
                        self._set_active_request(client, response)
                        self._raise_if_request_cancelled()
                        if response.status_code == 202:
                            raise ModelStreamError(
                                "AI provider queued the request without a "
                                "streaming result")
                        # On a non-2xx status, read the error body *inside*
                        # the stream context (before it closes) so the
                        # backend's detail survives into the HTTPStatusError
                        # handler below. raise_for_status() alone would leave
                        # the body unread and unreadable once the context
                        # exits, dropping the actionable detail.
                        if response.status_code >= 400:
                            try:
                                response.read()
                            except Exception:
                                pass
                        response.raise_for_status()
                        for line in response.iter_lines():
                            self._raise_if_request_cancelled()
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
            except httpx.ConnectError as exc:
                self._raise_if_request_cancelled()
                raise ModelUnavailableError(
                    f"Cannot connect to AI backend at {self._base_url}") from exc
            except httpx.HTTPStatusError as exc:
                retry_limit = self._rate_limit_retry_limit()
                if (exc.response.status_code == 429
                        and attempts < retry_limit):
                    attempts += 1
                    retry_after = exc.response.headers.get("retry-after")
                    try:
                        delay = max(0.25, float(retry_after or 0))
                    except ValueError:
                        delay = 0
                    if delay <= 0:
                        delay = (self.BUSY_RETRY_SECONDS
                                 if retry_limit == self.BUSY_RETRY_LIMIT
                                 else min(4.0, 2.0 ** attempts))
                    logger.info("Model returned 429; retry %d/%d in %.1fs",
                                attempts, retry_limit, delay)
                    self._interruptible_sleep(delay, on_delta)
                    continue
                detail = ""
                try:
                    exc.response.read()
                    detail = f": {exc.response.text[:300]}"
                except Exception:
                    pass
                if exc.response.status_code == 429:
                    raise ModelHTTPError(
                        "AI provider rate limit reached (HTTP 429). The API "
                        "key was accepted, but the provider has no capacity "
                        f"for this request right now{detail}") from exc
                if exc.response.status_code == 400 and has_image_input(messages):
                    raise ModelHTTPError(
                        "The selected model rejected image input (HTTP 400). "
                        "Choose a vision-capable model from the model selector "
                        f"and try again{detail}") from exc
                if exc.response.status_code == 404:
                    raise ModelHTTPError(
                        "AI backend returned HTTP 404 (Not Found). The model "
                        f"name {self._model!r} is not available on this "
                        f"backend, or the endpoint URL {url} is incorrect. "
                        "Verify the model is loaded and NEXA_MODEL / "
                        f"NEXA_API_URL are set correctly{detail}") from exc
                raise ModelHTTPError(
                    f"AI backend error: HTTP {exc.response.status_code}{detail}") from exc
            except AgentCancelledError:
                raise  # user cancel must not be masked as a stream error
            except ModelStreamError:
                raise
            except Exception as exc:
                self._raise_if_request_cancelled()
                raise ModelStreamError(f"AI stream interrupted: {exc}") from exc
            finally:
                self._clear_active_request(client)
            message = self._validate_agent_message(
                self.merge_stream_chunks(chunks))
            # Buffer until the turn is complete before forwarding prose.
            # Reasoning models can place the closing </think> marker in a
            # later chunk; streaming earlier chunks would leak private
            # reasoning before it becomes possible to identify the boundary.
            if on_delta and message.get("content"):
                on_delta(str(message["content"]))
            return message

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
                url = self._api_url("models")
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
