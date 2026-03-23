"""
Ollama LLM client — all LLM calls go through here.
Model: qwen3.5:27b via Ollama API.

IMPORTANT: num_predict is set high (32K) by default because Qwen 3.5 thinking
mode uses num_predict for BOTH thinking + response. Setting it low causes
thinking to exhaust the budget with zero response. 32K is safe — the model
stops generating when done, it doesn't fill all 32K tokens.
"""

import json
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen3.5:27b"
DEFAULT_CTX = 32768   # 32K context — 30 tok/s
DEFAULT_PREDICT = 24576  # 24K output — thinking up to 16K + response 6-8K
TIMEOUT = 3600  # 60 min


def generate(
    prompt: str,
    system: str = "",
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = DEFAULT_PREDICT,
    json_mode: bool = False,
    think: bool = True,
) -> str:
    """Generate text from Ollama. Returns raw string response.
    
    num_predict is set high (32K) to guarantee thinking mode never exhausts
    the output budget. The model stops when it's done — it won't waste tokens.
    """
    actual_prompt = prompt
    if not think:
        actual_prompt = f"/no_think\n{prompt}"

    payload = {
        "model": model,
        "prompt": actual_prompt,
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

        # If response is empty but thinking exists, model stopped after thinking
        if not response.strip() and thinking:
            logger.warning(f"Response empty despite {len(thinking)} chars thinking "
                         f"(eval_count={eval_count}, num_predict={max_tokens}). "
                         f"Retrying once with /no_think to force direct output.")
            # Retry WITHOUT thinking — forces model to write response directly
            payload["prompt"] = f"/no_think\n{prompt}"
            try:
                resp2 = requests.post(
                    f"{OLLAMA_HOST}/api/generate",
                    json=payload,
                    timeout=TIMEOUT,
                )
                resp2.raise_for_status()
                data2 = resp2.json()
                response2 = data2.get("response", "")
                if response2.strip():
                    logger.info(f"Retry without thinking succeeded: {len(response2.split())}w")
                    return response2
            except Exception as e2:
                logger.warning(f"Retry without thinking failed: {e2}")
            logger.error("Both thinking and /no_think attempts returned empty")
            return ""
        
        if not response.strip():
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
    """Generate and parse JSON from Ollama."""
    raw = generate(
        prompt=prompt,
        system=system,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=True,
        think=True,
    )
    if not raw or not raw.strip():
        logger.error("generate_json: empty response")
        return {}

    raw = raw.strip()
    # Strip ```json wrapper
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from mixed text
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
