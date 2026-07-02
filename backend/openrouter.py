"""OpenRouter API client for making LLM requests with rate-limit retries."""

import asyncio
import random
import httpx
from typing import List, Dict, Any, Optional
from .config import (
    OPENROUTER_API_KEY, OPENROUTER_API_URL, FALLBACK_MODELS,
    ANTHROPIC_API_KEY, ANTHROPIC_API_URL, CLAUDE_MODELS,
)


def _is_claude_model(model: str) -> bool:
    """Check if a model identifier refers to a Claude model."""
    return model.startswith("claude-")


def _resolve_claude_model(model: str) -> str:
    """Resolve a short Claude model name to the full Anthropic model ID."""
    return CLAUDE_MODELS.get(model, model)


async def _query_claude(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
) -> Optional[Dict[str, Any]]:
    """Query Claude via the Anthropic Messages API."""
    if not ANTHROPIC_API_KEY:
        print("[Claude] ANTHROPIC_API_KEY not set. Cannot query Claude.")
        return None

    resolved_model = _resolve_claude_model(model)

    # Anthropic API requires system prompt to be a top-level parameter
    system_prompt = None
    api_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_prompt = msg["content"]
        else:
            api_messages.append({"role": msg["role"], "content": msg["content"]})

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    payload = {
        "model": resolved_model,
        "max_tokens": 8192,
        "messages": api_messages,
    }
    if system_prompt:
        payload["system"] = system_prompt

    max_retries = 5
    base_delay = 3.0

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                print(f"[{model}] Rate limited. Retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries})...")
                await asyncio.sleep(delay)

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    ANTHROPIC_API_URL,
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 429:
                    continue

                response.raise_for_status()
                data = response.json()

                # Anthropic returns content as a list of blocks
                content_blocks = data.get("content", [])
                text_content = "\n".join(
                    block.get("text", "") for block in content_blocks if block.get("type") == "text"
                )

                return {
                    "content": text_content,
                    "reasoning_details": None,
                }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                continue
            print(f"HTTP error querying Claude model {model}: {e}")
            break
        except Exception as e:
            print(f"Error querying Claude model {model}: {e}")
            await asyncio.sleep(2.0)

    return None


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    attempted_models: Optional[set] = None
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via Gemini API (OpenAI compatibility endpoint),
    local Ollama, or Anthropic Claude API,
    with fallback support and automatic exponential backoff retry on 429 rate limits.
    """
    if attempted_models is None:
        attempted_models = {model}
    else:
        attempted_models.add(model)

    # Route to Claude handler if it's a Claude model
    if _is_claude_model(model):
        result = await _query_claude(model, messages, timeout)
        if result is not None:
            return result
        # Try fallbacks if Claude fails
        for fallback_model in FALLBACK_MODELS:
            if fallback_model not in attempted_models:
                print(f"Claude query failed for {model}. Falling back to {fallback_model}...")
                result = await query_model(
                    model=fallback_model,
                    messages=messages,
                    timeout=timeout,
                    attempted_models=attempted_models,
                )
                if result is not None:
                    return result
        return None

    # Dynamic routing: use local Ollama if model is qwen3:8b
    if model == "qwen3:8b":
        url = "http://localhost:11434/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        is_local = True
    else:
        url = OPENROUTER_API_URL
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        is_local = False

    payload = {
        "model": model,
        "messages": messages,
    }


    max_retries = 5 if not is_local else 2
    base_delay = 3.0

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                if is_local:
                    await asyncio.sleep(0.5)
                else:
                    delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                    print(f"[{model}] Rate limited (429). Retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(delay)

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload
                )

                # Handle rate limit explicitly
                if response.status_code == 429:
                    if is_local:
                        # Ollama shouldn't return 429, but handle it cleanly if it does
                        await asyncio.sleep(0.5)
                        continue
                    
                    # If daily/overall limit is hit, do not waste time retrying
                    if "PerDay" in response.text or "daily" in response.text.lower() or "limit: 20" in response.text:
                        print(f"[{model}] Daily quota exceeded. Skipping retries to fallback immediately.")
                        break
                        
                    continue

                response.raise_for_status()

                data = response.json()
                message = data['choices'][0]['message']

                return {
                    'content': message.get('content'),
                    'reasoning_details': message.get('reasoning_details')
                }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and not is_local:
                continue
            print(f"HTTP error querying model {model}: {e}")
            break
        except Exception as e:
            print(f"Error querying model {model}: {e}")
            # Wait briefly on network errors before retrying
            await asyncio.sleep(1.0 if is_local else 2.0)

    # If all retries failed or hit 429, try fallback models
    if not is_local:
        for fallback_model in FALLBACK_MODELS:
            if fallback_model not in attempted_models:
                print(f"All retries failed for {model}. Falling back to {fallback_model}...")
                result = await query_model(
                    model=fallback_model,
                    messages=messages,
                    timeout=timeout,
                    attempted_models=attempted_models
                )
                if result is not None:
                    print(f"Fallback to {fallback_model} succeeded!")
                    return result

    return None


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]]
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models sequentially with a stagger delay to avoid hitting rate limits.
    """
    responses = {}
    
    for i, model in enumerate(models):
        if i > 0:
            # Stagger requests by 5.5 seconds to stay under Google's 10 RPM limit
            print(f"Staggering next model query to prevent rate limits...")
            await asyncio.sleep(5.5)
            
        response = await query_model(model, messages)
        responses[model] = response
        
    return responses
