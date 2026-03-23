"""
Ollama LLM client — all LLM calls go through here.
Model: qwen3.5:27b via Ollama API.
"""

import json
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen3.5:27b"
DEFAULT_CTX = 32768  # 32K context — sweet spot for speed vs capacity
TIMEOUT = 1200  # 20 min — scripts can take long with thinking mode


def generate(
    prompt: str,
    system: str = "",
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    json_mode: bool = False,
) -> str:
    """Generate text from Ollama. Returns raw string response."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": DEFAULT_CTX,
        },
    }
    if system:
        payload["system"] = system
    if json_mode:
        payload["format"] = "json"

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json=payload,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        # Qwen 3.5 with thinking mode puts content in "thinking" when "response" is empty
        response = data.get("response", "")
        if not response.strip() and data.get("thinking"):
            response = data["thinking"]
        return response
    except requests.Timeout:
        logger.error(f"Ollama timeout after {TIMEOUT}s")
        raise
    except requests.ConnectionError:
        logger.error("Ollama not reachable — is it running?")
        raise
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        raise


def generate_json(
    prompt: str,
    system: str = "",
    model: str = DEFAULT_MODEL,
    temperature: float = 0.5,
    max_tokens: int = 8192,
) -> dict:
    """Generate and parse JSON from Ollama."""
    raw = generate(
        prompt=prompt,
        system=system,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=True,
    )
    # Try to parse JSON — handle edge cases
    raw = raw.strip()
    # Sometimes model wraps in ```json ... ```
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
        logger.error(f"Failed to parse JSON from LLM: {raw[:500]}")
        raise


def chat(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    json_mode: bool = False,
) -> str:
    """Chat-style generation with message history."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": DEFAULT_CTX,
        },
    }
    if json_mode:
        payload["format"] = "json"

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json=payload,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except Exception as e:
        logger.error(f"Ollama chat error: {e}")
        raise
