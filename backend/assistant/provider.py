"""Ollama JSON chat for the Phase 9 planner. Does not change Phase 6 generators."""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request

from backend.improvement.generators.ollama import (
    OllamaMalformed,
    OllamaModelUnavailable,
    OllamaTimeout,
    OllamaUnavailable,
    ollama_settings,
)

DEFAULT_ASSISTANT_MODEL = "llama3:latest"
DEFAULT_ASSISTANT_TIMEOUT = 30


def assistant_settings() -> tuple[str, str, int]:
    url, _phase6_model, _phase6_timeout = ollama_settings()
    model = os.getenv("CATALOGFORGE_ASSISTANT_OLLAMA_MODEL", DEFAULT_ASSISTANT_MODEL).strip() or DEFAULT_ASSISTANT_MODEL
    raw_timeout = os.getenv("CATALOGFORGE_ASSISTANT_OLLAMA_TIMEOUT", str(DEFAULT_ASSISTANT_TIMEOUT)).strip()
    try:
        timeout = int(raw_timeout)
    except ValueError:
        timeout = DEFAULT_ASSISTANT_TIMEOUT
    if timeout <= 0:
        timeout = DEFAULT_ASSISTANT_TIMEOUT
    return url.rstrip("/"), model, timeout


def chat_json(*, system: str, user: str) -> dict:
    """Return parsed JSON object from Ollama. Catalogue/review DATA must not be in these strings for the planner."""
    base_url, model, timeout = assistant_settings()
    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    request = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except TimeoutError as exc:
        raise OllamaTimeout("Ollama timed out.") from exc
    except socket.timeout as exc:
        raise OllamaTimeout("Ollama timed out.") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code in {404, 400} and "model" in detail.casefold():
            raise OllamaModelUnavailable("Ollama model unavailable") from exc
        raise OllamaUnavailable("Ollama unavailable") from exc
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        if "timed out" in reason.casefold():
            raise OllamaTimeout("Ollama timed out.") from exc
        raise OllamaUnavailable("Ollama unavailable") from exc
    except OSError as exc:
        raise OllamaUnavailable("Ollama unavailable") from exc
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OllamaMalformed("malformed JSON") from exc
    if isinstance(envelope, dict) and envelope.get("error"):
        error = str(envelope["error"])
        if "not found" in error.casefold() or "model" in error.casefold():
            raise OllamaModelUnavailable("Ollama model unavailable")
        raise OllamaUnavailable("Ollama unavailable")
    message = envelope.get("message") if isinstance(envelope, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise OllamaMalformed("malformed JSON")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise OllamaMalformed("malformed JSON") from exc
    if not isinstance(parsed, dict):
        raise OllamaMalformed("malformed JSON")
    return parsed
