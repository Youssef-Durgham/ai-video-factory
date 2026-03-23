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

    # Auto-retry with more tokens if thinking exhausts the budget
    current_predict = max_tokens
    max_retries = 3
    
    for attempt in range(max_retries + 1):
        payload["options"]["num_predict"] = current_predict
        
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
                logger.debug(f"Thinking: {len(thinking)} chars, Response: {len(response)} chars, "
                           f"eval_count: {eval_count}, num_predict: {current_predict}")
            
            # If response is empty but thinking exists → thinking ate all tokens
            if not response.strip() and thinking:
                if attempt < max_retries:
                    # Double the token budget and retry
                    old_predict = current_predict
                    current_predict = min(current_predict * 2, 65536)  # Cap at 64K
                    logger.warning(f"Thinking exhausted tokens ({len(thinking)} chars thinking, 0 response). "
                                 f"Retrying: num_predict {old_predict} → {current_predict} (attempt {attempt+2}/{max_retries+1})")
                    continue
                else:
                    logger.error(f"Thinking exhausted tokens after {max_retries+1} attempts "
                               f"(last num_predict={current_predict}). Returning empty.")
                    return ""
            
            if not response.strip() and not thinking:
                return ""
            
            return response
            
        except requests.Timeout:
            logger.error(f"Ollama timeout after {TIMEOUT}s (num_predict={current_predict})")
            raise
        except requests.ConnectionError:
            logger.error("Ollama not reachable — is it running?")
            raise
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise
    
    return ""


def generate_json(
    prompt: str,
    system: str = "",
    model: str = DEFAULT_MODEL,
    temperature: float = 0.5,
    max_tokens: int = 8192,
    retries: int = 2,
) -> dict:
    """Generate and parse JSON from Ollama. generate() auto-retries if thinking exhausts tokens."""
    raw = generate(
        prompt=prompt,
        system=system,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=True,
        think=True,  # Always thinking — generate() handles token exhaustion internally
    )
    if not raw or not raw.strip():
        logger.error("generate_json: empty response after all retries")
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
