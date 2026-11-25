import pytest

from glucolit.llm.gateway import (
    CircuitBreaker,
    FakeLLM,
    LLMError,
    LLMGateway,
    LLMUnavailable,
)


@pytest.mark.asyncio
async def test_generate_success():
    fake = FakeLLM(script=["Hello"])
    gateway = LLMGateway([fake])

    result = await gateway.generate([{"role": "user", "content": "Hi"}])

    assert result.text == "Hello"
    assert result.provider == "fake"
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_generate_fallback():
    primary = FakeLLM(name="gemini", script=[LLMError("Primary failed", retryable=False)])
    fallback = FakeLLM(name="groq", script=["Fallback answer"])

    gateway = LLMGateway([primary, fallback])

    result = await gateway.generate([{"role": "user", "content": "Hi"}])

    assert result.text == "Fallback answer"
    assert result.provider == "groq"
    assert result.fallback_used is True


@pytest.mark.asyncio
async def test_generate_unavailable():
    primary = FakeLLM(script=[LLMError("Failed", retryable=False)])
    gateway = LLMGateway([primary])

    with pytest.raises(LLMUnavailable):
        await gateway.generate([{"role": "user", "content": "Hi"}])


@pytest.mark.asyncio
async def test_stream_success():
    fake = FakeLLM(script=["Hello world"])
    gateway = LLMGateway([fake])

    items = [item async for item in gateway.stream([{"role": "user", "content": "Hi"}])]

    assert "".join(item for item in items if isinstance(item, str)).strip() == "Hello world"
    assert items[-1].text.strip() == "Hello world"


def test_circuit_breaker():
    now = [0.0]
    breaker = CircuitBreaker(
        threshold=2,
        cooldown=10,
        clock=lambda: now[0],
    )

    assert breaker.allow()

    breaker.failure()
    breaker.failure()

    assert not breaker.allow()

    now[0] = 11.0
    assert breaker.allow()

    breaker.success()
    assert breaker.state == "closed"


@pytest.mark.asyncio
async def test_usage_recorder():
    records = []

    async def recorder(row):
        records.append(row)

    fake = FakeLLM(script=["Recorded answer"])
    gateway = LLMGateway([fake], recorder=recorder)

    await gateway.generate(
        [{"role": "user", "content": "Hi"}],
        purpose="chat",
        prompt_version="v1",
    )

    assert len(records) == 1
    assert records[0]["status"] == "ok"
    assert records[0]["purpose"] == "chat"
    assert records[0]["prompt_version"] == "v1"
