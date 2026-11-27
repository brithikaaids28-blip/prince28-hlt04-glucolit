"""Protected API endpoints for background ingestion jobs."""

import secrets
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from glucolit.api.deps import get_session
from glucolit.config import get_settings
from glucolit.db.models import IngestItem, IngestJob
from glucolit.ingest.fetch import read_sources
from glucolit.ingest.queue import enqueue_ingest

router = APIRouter(prefix="/v1/ingest", tags=["ingestion"])


class IngestRequest(BaseModel):
    """Request options for creating an ingestion job."""

    limit: int = Field(default=20, ge=1, le=2000)
    source: str | None = Field(default=None, min_length=1)
    retry_failed: bool = False


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


async def submit_job(
    session: AsyncSession,
    records: list[dict],
) -> dict:
    """Create a database job and submit it to Redis."""
    if not records:
        return {
            "job_id": None,
            "queue_job_id": None,
            "requested": 0,
            "status": "no_work",
        }

    job_id = uuid4().hex
    job = IngestJob(id=job_id, requested=len(records))
    session.add(job)

    for record in records:
        session.add(
            IngestItem(
                job_id=job_id,
                record=record,
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
        "requested": len(records),
        "status": "queued",
    }


async def create_job_from_sources(
    session: AsyncSession,
    limit: int,
    source: str | None,
    response: Response,
) -> dict:
    """Select eligible sources and submit them as a job."""
    try:
        sources = read_sources()
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read source list: {exc}",
        ) from exc

    eligible_sources = [
        item
        for item in sources
        if "NC-ND" not in item.licence.upper()
        and (source is None or item.source.casefold() == source.casefold())
    ]

    selected_sources = eligible_sources[:limit]

    records = [
        {
            "url": item.url,
            "source": item.source,
            "licence": item.licence,
            "title": item.title,
        }
        for item in selected_sources
    ]

    result = await submit_job(session, records)

    if result["requested"] == 0:
        response.status_code = status.HTTP_200_OK

    return result


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_ingest_job(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    body: IngestRequest | None = None,
    limit: Annotated[int | None, Query(ge=1, le=2000)] = None,
    source: Annotated[str | None, Query(min_length=1)] = None,
    retry_failed: Annotated[bool | None, Query()] = None,
    admin_token: Annotated[str, Header(alias="X-Admin-Token")] = "",
):
    """Create a new ingestion job from eligible source records."""
    verify_admin(admin_token)

    # JSON body takes precedence; query parameters remain supported.
    request = body or IngestRequest()

    selected_limit = limit if limit is not None else request.limit
    selected_source = source if source is not None else request.source
    selected_retry = retry_failed if retry_failed is not None else request.retry_failed

    if selected_retry:
        raise HTTPException(
            status_code=400,
            detail=("Specify the original job ID using POST /v1/ingest/{job_id}/retry"),
        )

    return await create_job_from_sources(
        session,
        selected_limit,
        selected_source,
        response,
    )


@router.post("/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_failed_items(
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_token: Annotated[str, Header(alias="X-Admin-Token")] = "",
):
    """Create a separate job containing copies of failed source records."""
    verify_admin(admin_token)

    original_job = await session.get(IngestJob, job_id)

    if original_job is None:
        raise HTTPException(
            status_code=404,
            detail="Ingestion job not found",
        )

    result = await session.execute(
        select(IngestItem)
        .where(
            IngestItem.job_id == job_id,
            IngestItem.status == "failed",
        )
        .order_by(IngestItem.id)
    )

    failed_items = result.scalars().all()
    records = [dict(item.record) for item in failed_items]

    if not records:
        raise HTTPException(
            status_code=409,
            detail="This job has no failed items to retry",
        )

    return await submit_job(session, records)


@router.get("/dead-letter")
async def get_dead_letter_items(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    admin_token: Annotated[str, Header(alias="X-Admin-Token")] = "",
):
    """List failed ingestion items for inspection."""
    verify_admin(admin_token)

    result = await session.execute(
        select(IngestItem)
        .where(IngestItem.status == "failed")
        .order_by(IngestItem.updated_at.desc())
        .limit(limit)
    )

    items = result.scalars().all()

    return {
        "count": len(items),
        "items": [
            {
                "id": item.id,
                "job_id": item.job_id,
                "source": item.record.get("source"),
                "title": item.record.get("title"),
                "status": item.status,
                "attempts": item.attempts,
                "error": item.error,
                "updated_at": (item.updated_at.isoformat() if item.updated_at else None),
            }
            for item in items
        ],
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
        job_status = "processing" if counts["processing"] else "queued"
    elif counts["failed"] and counts["done"]:
        job_status = "completed_with_errors"
    elif counts["failed"]:
        job_status = "failed"
    else:
        job_status = "completed"

    return {
        "job_id": job.id,
        "requested": job.requested,
        "status": job_status,
        "counts": counts,
        "items": item_details,
    }
