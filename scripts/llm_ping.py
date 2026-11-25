"""Test Gemini and Groq API connections using direct HTTP requests."""

import time

import httpx

from glucolit.config import get_settings


def ping_provider(
    name: str,
    api_key: str,
    base_url: str,
    model: str,
    timeout: float,
) -> None:
    if not api_key:
        print(f"{name:<8} FAILED   API key is missing")
        return

    url = f"{base_url.rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with only the word pong."}],
        "max_tokens": 256,
    }

    try:
        start = time.perf_counter()

        response = httpx.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )

        elapsed = int((time.perf_counter() - start) * 1000)
        response.raise_for_status()

        result = response.json()
        answer = result["choices"][0]["message"]["content"]

        usage = result.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        print(
            f"{name:<8} OK       {model} said "
            f"'{answer}' in {elapsed} ms, "
            f"tokens in={input_tokens} out={output_tokens}"
        )

    except httpx.HTTPStatusError as exc:
        print(f"{name:<8} FAILED   HTTP {exc.response.status_code}: {exc.response.text[:300]}")

    except Exception as exc:
        print(f"{name:<8} FAILED   {type(exc).__name__}: {exc}")


def main() -> None:
    settings = get_settings()

    ping_provider(
        "gemini",
        settings.gemini_api_key,
        settings.llm_primary_base_url,
        settings.llm_primary_model,
        settings.llm_timeout_seconds,
    )

    ping_provider(
        "groq",
        settings.groq_api_key,
        settings.llm_fallback_base_url,
        settings.llm_fallback_model,
        settings.llm_timeout_seconds,
    )


if __name__ == "__main__":
    main()
