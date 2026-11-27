"""Protected API endpoints for background ingestion jobs."""

import secrets
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from glucolit.api.deps import get_session
from glucolit.config import get_settings
from glucolit.db.models import IngestItem, IngestJob
from glucolit.ingest.fetch import read_sources
from glucolit.ingest.queue import enqueue_ingest

router = APIRouter(prefix="/v1/ingest", tags=["ingestion"])


def verify_admin(token: str) -> None:
    """Verify the admin token without exposing its value."""
    expected = get_settings().admin_token

    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Admin authentication is not configured",
        )

    if not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid admin token",
        )


@router.post("")
async def create_ingest_job(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=10)] = 1,
    admin_token: Annotated[str, Header(alias="X-Admin-Token")] = "",
):
    """Create an ingestion job and submit it to Redis."""
    verify_admin(admin_token)

    try:
        sources = read_sources()
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read source list: {exc}",
        ) from exc

    eligible_sources = [source for source in sources if "NC-ND" not in source.licence.upper()]

    selected_sources = eligible_sources[:limit]

    if not selected_sources:
        raise HTTPException(
            status_code=400,
            detail="No eligible sources are available for ingestion",
        )

    job_id = uuid4().hex

    job = IngestJob(
        id=job_id,
        requested=len(selected_sources),
    )

    session.add(job)

    for source in selected_sources:
        session.add(
            IngestItem(
                job_id=job_id,
                record={
                    "url": source.url,
                    "source": source.source,
                    "licence": source.licence,
                    "title": source.title,
                },
                status="queued",
            )
        )

    await session.commit()

    try:
        queue_job_id = await enqueue_ingest(job_id)
    except Exception as exc:
        await session.execute(delete(IngestItem).where(IngestItem.job_id == job_id))
        await session.delete(job)
        await session.commit()

        raise HTTPException(
            status_code=503,
            detail="Could not submit ingestion job to Redis",
        ) from exc

    return {
        "job_id": job_id,
        "queue_job_id": queue_job_id,
        "requested": len(selected_sources),
        "status": "queued",
    }


@router.get("/{job_id}")
async def get_ingest_job(
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_token: Annotated[str, Header(alias="X-Admin-Token")] = "",
):
    """Get ingestion job progress and individual item statuses."""
    verify_admin(admin_token)

    job = await session.get(IngestJob, job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Ingestion job not found",
        )

    result = await session.execute(
        select(IngestItem).where(IngestItem.job_id == job_id).order_by(IngestItem.id)
    )

    items = result.scalars().all()

    counts = {
        "queued": 0,
        "processing": 0,
        "done": 0,
        "failed": 0,
    }

    item_details = []

    for item in items:
        if item.status in counts:
            counts[item.status] += 1

        item_details.append(
            {
                "id": item.id,
                "source": item.record.get("source"),
                "title": item.record.get("title"),
                "status": item.status,
                "attempts": item.attempts,
                "pages": item.pages,
                "error": item.error,
            }
        )

    if counts["queued"] or counts["processing"]:
        status = "processing" if counts["processing"] else "queued"
    elif counts["failed"] and counts["done"]:
        status = "completed_with_errors"
    elif counts["failed"]:
        status = "failed"
    else:
        status = "completed"

    return {
        "job_id": job.id,
        "requested": job.requested,
        "status": status,
        "counts": counts,
        "items": item_details,
    }
