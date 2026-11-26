"""Provider-neutral LLM gateway with retries, fallback, streaming and usage recording."""

import asyncio
import logging
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import httpx

from glucolit.config import Settings

Message = dict[str, str]
Recorder = Callable[[dict], Awaitable[None]]

log = logging.getLogger(__name__)


class LLMError(Exception):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


class LLMUnavailable(Exception):
    pass


@dataclass
class Reply:
    text: str = ""
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_inr: float
    attempts: int
    fallback_used: bool


def cost_inr(model: str, tokens_in: int, tokens_out: int, usd_inr: float) -> float:
    """Calculate estimated API cost in INR."""
    prices = {
        "gemini-3.8-flash": (0.75, 3.75),
        "llama-3.3-70b-versatile": (0.59, 0.79),
    }
    if model not in prices:
        return 0.0

    input_price, output_price = prices[model]
    usd = (tokens_in * input_price + tokens_out * output_price) / 1_000_000
    return round(usd * usd_inr, 4)


def estimate_tokens(text: str) -> int:
    """Roughly estimate tokens from text length."""
    return max(1, (len(text) + 3) // 4)


class OpenAICompatProvider:
    """Provider using the OpenAI-compatible chat completions API."""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ):
        self.name = name
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0))

    def _body(
        self,
        messages: list[Message],
        temperature: float,
        stream: bool,
        response_format: dict | None = None,
    ) -> dict:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format is not None:
            body["response_format"] = response_format
        if stream:
            body |= {
                "stream": True,
                "stream_options": {"include_usage": True},
            }
        return body

    @staticmethod
    def _error(response: httpx.Response) -> LLMError:
        code = response.status_code
        wait = response.headers.get("retry-after", "")
        return LLMError(
            f"HTTP {code}: {response.text[:200]}",
            retryable=code in {408, 429} or code >= 500,
            retry_after=float(wait) if wait.replace(".", "", 1).isdigit() else None,
        )

    @staticmethod
    def _network_error(exc: httpx.TransportError) -> LLMError:
        timed_out = isinstance(exc, httpx.TimeoutException)
        return LLMError(type(exc).__name__, retryable=not timed_out)

    async def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        response_format: dict | None = None,
    ) -> Reply:
        body = self._body(
            messages,
            temperature,
            stream=False,
            response_format=response_format,
        )
        try:
            response = await self._client.post(
                self._url,
                headers=self._headers,
                json=body,
            )
        except httpx.TransportError as exc:
            raise self._network_error(exc) from exc

        if response.status_code != 200:
            raise self._error(response)

        data = response.json()
        usage = data.get("usage") or {}
        text = data["choices"][0]["message"].get("content") or ""

        return Reply(
            text,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )

    async def stream(
        self,
        messages: list[Message],
        usage: Reply,
        *,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """Yield answer pieces and fill usage at the end."""
        body = self._body(messages, temperature, stream=True)

        try:
            async with self._client.stream(
                "POST",
                self._url,
                headers=self._headers,
                json=body,
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise self._error(response)

                finished = False

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue

                    payload = line[5:].strip()

                    if payload == "[DONE]":
                        finished = True
                        break

                    try:
                        data = __import__("json").loads(payload)
                    except ValueError:
                        continue

                    counts = data.get("usage") or {}
                    if counts:
                        usage.tokens_in = counts.get("prompt_tokens", 0)
                        usage.tokens_out = counts.get("completion_tokens", 0)

                    choices = data.get("choices") or []
                    if not choices:
                        continue

                    choice = choices[0]
                    content = (choice.get("delta") or {}).get("content")

                    if content:
                        yield content

                    if choice.get("finish_reason"):
                        finished = True

                if not finished:
                    raise LLMError(
                        "Stream ended early without a finish signal",
                        retryable=False,
                    )

        except httpx.TransportError as exc:
            raise self._network_error(exc) from exc


class FakeLLM:
    """A scripted provider for tests: no network and no API bill."""

    def __init__(
        self,
        name: str = "fake",
        model: str = "fake-1",
        script: list | None = None,
    ):
        self.name = name
        self.model = model
        self.script = list(script or [])
        self.calls = 0
        self.seen = []

    def _next(self) -> object:
        self.calls += 1
        return self.script.pop(0) if self.script else "A fake answer."

    async def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        **options,
    ) -> Reply:
        self.seen.append(
            {
                "messages": messages,
                "temperature": temperature,
                **options,
            }
        )

        item = self._next()
        if isinstance(item, Exception):
            raise item

        return Reply(
            str(item),
            tokens_in=12,
            tokens_out=len(str(item).split()),
        )

    async def stream(
        self,
        messages: list[Message],
        usage: Reply,
        *,
        temperature: float = 0.2,
        **options,
    ) -> AsyncIterator[str]:
        item = self._next()

        if isinstance(item, Exception):
            raise item

        error = item[1] if isinstance(item, tuple) else None
        words = ("Half an answer" if error else str(item)).split()

        for word in words:
            yield word + " "

        if error:
            raise error

        usage.tokens_in = 12
        usage.tokens_out = len(words)


class CircuitBreaker:
    """Stops calls to a provider that repeatedly fails."""

    def __init__(
        self,
        threshold: int = 3,
        cooldown: float = 30.0,
        clock=time.monotonic,
    ) -> None:
        self.threshold = threshold
        self.cooldown = cooldown
        self.clock = clock
        self.failures = 0
        self.opened_at = 0.0
        self._state = "closed"

    @property
    def state(self) -> str:
        if self._state == "open" and self.clock() - self.opened_at >= self.cooldown:
            return "half-open"
        return self._state

    def allow(self) -> bool:
        return self.state != "open"

    def success(self) -> None:
        self.failures = 0
        self._state = "closed"

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold or self._state == "half-open":
            self._state = "open"
            self.opened_at = self.clock()


class LLMGateway:
    """Routes calls through providers with retries and fallback."""

    def __init__(
        self,
        providers: list,
        *,
        recorder: Recorder | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock=time.monotonic,
        breaker_threshold: int = 3,
        breaker_cooldown: float = 30.0,
    ):
        self.providers = providers
        self.recorder = recorder
        self.sleep = sleep
        self.clock = clock
        self.breakers = {
            provider.name: CircuitBreaker(
                breaker_threshold,
                breaker_cooldown,
                clock,
            )
            for provider in providers
        }

    async def _record(
        self,
        provider,
        purpose: str,
        prompt_version: str,
        **fields,
    ) -> None:
        if not self.recorder:
            return

        row = {
            "provider": provider.name,
            "model": provider.model,
            "purpose": purpose,
            "prompt_version": prompt_version,
            **fields,
        }

        try:
            await self.recorder(row)
        except Exception:
            log.exception("LLM usage recorder failed")

    def _result(
        self,
        provider,
        messages,
        reply: Reply,
        started: float,
        attempts: int,
        index: int,
    ):
        if not reply.tokens_in:
            reply.tokens_in = estimate_tokens(" ".join(message["content"] for message in messages))

        if not reply.tokens_out:
            reply.tokens_out = estimate_tokens(reply.text)

        return LLMResult(
            text=reply.text,
            provider=provider.name,
            model=provider.model,
            tokens_in=reply.tokens_in,
            tokens_out=reply.tokens_out,
            cost_inr=cost_inr(provider.model, reply.tokens_in, reply.tokens_out, 95.0),
            attempts=attempts,
            fallback_used=index > 0,
        )

    @staticmethod
    def _fields(result: LLMResult) -> dict:
        return {
            "status": "ok",
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "cost_inr": result.cost_inr,
        }

    async def generate(
        self,
        messages: list[Message],
        *,
        purpose: str = "chat",
        prompt_version: str = "",
        **options,
    ) -> LLMResult:
        errors = []

        for index, provider in enumerate(self.providers):
            breaker = self.breakers[provider.name]

            if not breaker.allow():
                errors.append(f"{provider.name}: circuit open")
                continue

            started = self.clock()

            for attempt, attempts in enumerate(range(1, 3)):
                try:
                    reply = await provider.generate(messages, **options)
                    result = self._result(
                        provider,
                        messages,
                        reply,
                        started,
                        attempts,
                        index,
                    )
                    breaker.success()

                    await self._record(
                        provider,
                        purpose,
                        prompt_version,
                        **self._fields(result),
                    )
                    return result

                except LLMError as exc:
                    errors.append(f"{provider.name}: {exc}")
                    breaker.failure()

                    if not exc.retryable or attempt == 1:
                        break

                    delay = exc.retry_after or random.uniform(0.5, 1.5)
                    await self.sleep(delay)

                except Exception as exc:
                    errors.append(f"{provider.name}: {exc}")
                    breaker.failure()
                    break

            await self._record(
                provider,
                purpose,
                prompt_version,
                status="error",
                error=str(errors[-1]),
            )

        raise LLMUnavailable("; ".join(errors) or "no LLM provider configured")

    async def stream(
        self,
        messages: list[Message],
        *,
        purpose: str = "chat",
        prompt_version: str = "",
        **options,
    ) -> AsyncIterator[str | LLMResult]:
        errors = []

        for index, provider in enumerate(self.providers):
            breaker = self.breakers[provider.name]

            if not breaker.allow():
                errors.append(f"{provider.name}: circuit open")
                continue

            started = self.clock()
            usage = Reply()
            sent = False
            full_text = ""

            try:
                async for piece in provider.stream(messages, usage, **options):
                    sent = True
                    full_text += piece
                    yield piece

                result = self._result(
                    provider,
                    messages,
                    Reply(full_text, usage.tokens_in, usage.tokens_out),
                    started,
                    1,
                    index,
                )
                breaker.success()

                await self._record(
                    provider,
                    purpose,
                    prompt_version,
                    **self._fields(result),
                )
                yield result
                return

            except LLMError as exc:
                errors.append(f"{provider.name}: {exc}")
                breaker.failure()

                if sent:
                    raise LLMUnavailable(f"Stream failed mid-answer: {exc}") from exc

            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
                breaker.failure()

                if sent:
                    raise LLMUnavailable(f"Stream failed mid-answer: {exc}") from exc

            await self._record(
                provider,
                purpose,
                prompt_version,
                status="error",
                error=str(errors[-1]),
            )

        raise LLMUnavailable("; ".join(errors) or "no LLM provider configured")


def build_gateway(
    settings: Settings,
    recorder: Recorder | None = None,
) -> LLMGateway:
    """Build the configured primary and fallback providers."""
    providers = []

    if settings.gemini_api_key:
        providers.append(
            OpenAICompatProvider(
                "gemini",
                settings.llm_primary_base_url,
                settings.gemini_api_key,
                settings.llm_primary_model,
                timeout=settings.llm_timeout_seconds,
            )
        )

    if settings.groq_api_key:
        providers.append(
            OpenAICompatProvider(
                "groq",
                settings.llm_fallback_base_url,
                settings.groq_api_key,
                settings.llm_fallback_model,
                timeout=settings.llm_timeout_seconds,
            )
        )

    return LLMGateway(providers, recorder=recorder)
