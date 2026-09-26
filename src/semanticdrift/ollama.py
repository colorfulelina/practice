"""Ollama REST client (methodology §8.3). Same /api/chat call, no LangGraph yet."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
GENERATOR_MODEL = "qwen2.5-coder:7b"
VALIDATOR_MODEL = "deepseek-coder-v2:lite"
DEFAULT_TIMEOUT = 180


class OllamaError(RuntimeError):
    pass


def chat(
    model: str,
    messages: List[Dict[str, str]],
    timeout: int = DEFAULT_TIMEOUT,
    base_url: Optional[str] = None,
) -> str:
    url = (base_url or OLLAMA_URL).rstrip("/") + "/api/chat"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise OllamaError(
            f"Cannot reach Ollama at {url}. Start it with: ollama serve"
        ) from exc
    try:
        content = body["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise OllamaError(f"Unexpected Ollama response: {body!r}") from exc
    if not isinstance(content, str) or not content.strip():
        raise OllamaError("Ollama returned an empty message")
    return content
