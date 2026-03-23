"""
Ollama LLM client — all LLM calls go through here.
Model: qwen3.5:27b via Ollama API.

Thinking mode is ALWAYS ON. No exceptions. No /no_think anywhere.
If a call fails, we retry with a simpler/shorter prompt — never by disabling thinking.
"""

import json
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen3.5:27b"
DEFAULT_CTX = 32768   # 32K context — 30 tok/s
DEFAULT_PREDICT = 24576  # 24K output — thinking + response
TIMEOUT = 3600  # 60 min


def generate(
    prompt: str,
    system: str = "",
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = DEFAULT_PREDICT,
    json_mode: bool = False,
) -> str:
    """Generate text from Ollama. Always with thinking. Returns response text only."""
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
        response = data.get("response", "")
        thinking = data.get("thinking", "")
        eval_count = data.get("eval_count", 0)

        if thinking:
            think_words = len(thinking.split())
            resp_words = len(response.split()) if response else 0
            logger.info(f"LLM: thinking={think_words}w, response={resp_words}w, "
                       f"eval_count={eval_count}, num_predict={max_tokens}")

        if not response.strip():
            if thinking:
                logger.warning(f"Response empty — thinking used {eval_count}/{max_tokens} tokens")
            return ""

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
    max_tokens: int = DEFAULT_PREDICT,
) -> dict:
    """Generate and parse JSON from Ollama. Always with thinking."""
    raw = generate(
        prompt=prompt,
        system=system,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=True,
    )
    if not raw or not raw.strip():
        logger.error("generate_json: empty response")
        return {}

    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        for opener, closer in [("{", "}"), ("[", "]")]:
            start = raw.find(opener)
            end = raw.rfind(closer) + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(raw[start:end])
                except json.JSONDecodeError:
                    continue
        logger.error(f"Failed to parse JSON: {raw[:500]}")
        return {}


def chat(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = DEFAULT_PREDICT,
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
