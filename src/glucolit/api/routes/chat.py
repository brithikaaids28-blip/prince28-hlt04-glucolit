"""Chat and LLM usage API endpoints."""

import json
from collections.abc import AsyncIterator
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from glucolit.api.deps import GatewayDep, UsageDep
from glucolit.llm.gateway import LLMResult, LLMUnavailable

router = APIRouter(prefix="/v1", tags=["chat"])

PROMPT_VERSION = "chat_system_v1"


def load_prompt(directory: Path, name: str = PROMPT_VERSION) -> str:
    """Load a versioned system prompt from a Markdown file."""
    return (directory / f"{name}.md").read_text(encoding="utf-8").strip()


class ChatRequest(BaseModel):
    """Incoming chat request."""

    message: str = Field(min_length=1, max_length=4000)
    stream: bool = True


def sse(data: dict, event: str = "") -> str:
    """Format one server-sent event."""
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(data, ensure_ascii=False)}\n\n"


def result_summary(result: LLMResult) -> dict:
    """Return result metadata without the answer text."""
    data = asdict(result)
    data.pop("text", None)
    return data


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    gateway: GatewayDep,
):
    """Answer a chat question, optionally as a server-sent event stream."""
    messages = [
        {
            "role": "system",
            "content": request.app.state.system_prompt,
        },
        {
            "role": "user",
            "content": body.message,
        },
    ]

    if not body.stream:
        try:
            result = await gateway.generate(
                messages,
                purpose="chat",
                prompt_version=PROMPT_VERSION,
            )
        except LLMUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        return {
            "answer": result.text,
            "usage": result_summary(result),
        }

    stream = gateway.stream(
        messages,
        purpose="chat",
        prompt_version=PROMPT_VERSION,
    )

    try:
        first = await anext(stream)
    except LLMUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    async def events() -> AsyncIterator[str]:
        try:
            items = _prepend(first, stream)
            async for item in items:
                if isinstance(item, LLMResult):
                    yield sse(result_summary(item), "done")
                else:
                    yield sse({"delta": item}, "delta")
        except LLMUnavailable as exc:
            yield sse({"error": str(exc)}, "error")

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _prepend(first, stream) -> AsyncIterator:
    """Yield the first stream item, then the remaining items."""
    yield first
    async for item in stream:
        yield item


@router.get("/usage")
async def usage(
    repository: UsageDep,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
):
    """Return daily LLM usage and total estimated cost."""
    rows = await repository.by_day(days)
    return {
        "days": rows,
        "total_cost_inr": round(sum(row["cost_inr"] for row in rows), 4),
        "calls": sum(row["calls"] for row in rows),
    }
