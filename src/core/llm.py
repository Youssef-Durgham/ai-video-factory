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
TIMEOUT = 3600  # 60 min — thinking mode can take very long on complex topics


def generate(
    prompt: str,
    system: str = "",
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    json_mode: bool = False,
    think: bool = True,
) -> str:
    """Generate text from Ollama. Returns raw string response.
    
    Args:
        think: Enable/disable thinking mode. Disable for long-form creative
               writing to avoid thinking consuming the output token budget.
    """
    # Qwen 3.5 thinking mode: /no_think disables internal reasoning
    # This is critical for scripts — thinking eats 80%+ of num_predict budget
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
        
        # Log token usage for debugging
        eval_count = data.get("eval_count", 0)
        if thinking:
            logger.debug(f"Thinking: {len(thinking)} chars, Response: {len(response)} chars, eval_count: {eval_count}")
        
        # If response is empty but thinking exists, the model spent all tokens thinking.
        # Do NOT use thinking as response — it's internal reasoning (often in English).
        if not response.strip():
            if thinking:
                logger.warning(f"Response empty but thinking has {len(thinking)} chars — model exhausted tokens on thinking. Returning empty.")
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
    max_tokens: int = 8192,
    retries: int = 2,
) -> dict:
    """Generate and parse JSON from Ollama. Retries on empty/invalid response."""
    for attempt in range(retries + 1):
        raw = generate(
            prompt=prompt,
            system=system,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        if raw and raw.strip():
            break
        if attempt < retries:
            logger.warning(f"generate_json: empty response (attempt {attempt+1}/{retries+1}), retrying with more tokens")
            max_tokens = min(max_tokens * 2, 32768)  # Double tokens each retry
        else:
            logger.error("generate_json: all retries returned empty response")
            return {}
    
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
        return {}


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
