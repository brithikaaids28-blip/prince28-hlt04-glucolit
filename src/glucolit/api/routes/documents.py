"""Document API endpoints."""

from fastapi import APIRouter, HTTPException, Query, Request

from glucolit.api.deps import RepositoryDep
from glucolit.api.errors import DocumentNotFoundError
from glucolit.db.repository import FILTER_KEY

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.get("")
async def list_documents(
    request: Request,
    repository: RepositoryDep,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None),
):
    """List documents with search, metadata filters, and pagination."""

    reserved = {"q", "limit", "offset"}

    filters = {key: value for key, value in request.query_params.items() if key not in reserved}

    for key in filters:
        if not FILTER_KEY.fullmatch(key):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid filter name: {key}",
            )

    total, documents = await repository.list(
        q=q,
        filters=filters,
        limit=limit,
        offset=offset,
    )

    return {
        "items": documents,
        "total": total,
        "filters": filters,
    }


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    repository: RepositoryDep,
):
    """Get one document by its external ID."""

    document = await repository.get(document_id)

    if document is None:
        raise DocumentNotFoundError(document_id)

    return document
