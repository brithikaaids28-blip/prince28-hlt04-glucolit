"""Database recorder and usage summaries for LLM calls."""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from glucolit.db.models import LlmCall


class LLMCallRepository:
    """Write LLM call records and summarize daily usage."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def record(self, row: dict) -> None:
        """Store one successful or failed provider call."""
        async with self.sessions() as session:
            session.add(LlmCall(**row))
            await session.commit()

    async def by_day(self, days: int = 7) -> list[dict]:
        """Return daily call counts, errors, fallbacks and estimated INR cost."""
        start = date.today() - timedelta(days=days - 1)

        async with self.sessions() as session:
            statement = (
                select(
                    func.date(LlmCall.created_at).label("day"),
                    func.count(LlmCall.id).label("calls"),
                    func.count(LlmCall.id).filter(LlmCall.status == "error").label("errors"),
                    func.count(LlmCall.id)
                    .filter(LlmCall.fallback_used.is_(True))
                    .label("fallbacks"),
                    func.sum(LlmCall.cost_inr).label("cost_inr"),
                )
                .where(LlmCall.created_at >= start)
                .group_by(func.date(LlmCall.created_at))
                .order_by(func.date(LlmCall.created_at))
            )

            result = await session.execute(statement)

            return [
                {
                    "day": str(row.day),
                    "calls": row.calls,
                    "errors": row.errors or 0,
                    "fallbacks": row.fallbacks or 0,
                    "cost_inr": round(float(row.cost_inr or 0), 6),
                }
                for row in result
            ]
