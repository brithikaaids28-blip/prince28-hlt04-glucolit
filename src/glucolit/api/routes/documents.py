"""Document API endpoints."""

from fastapi import APIRouter, Query

from glucolit.api.deps import StoreDep
from glucolit.api.errors import DocumentNotFoundError

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.get("")
def list_documents(
    store: StoreDep,
    limit: int = Query(default=10, ge=1, le=100),
    q: str | None = Query(default=None),
):
    documents = store.list_documents(100)

    if q:
        search_text = q.lower()
        documents = [
            document for document in documents if search_text in document.get("title", "").lower()
        ]

    total = len(documents)

    return {
        "items": documents[:limit],
        "total": total,
    }


@router.get("/{document_id}")
def get_document(document_id: str, store: StoreDep):
    document = store.get_document(document_id)

    if document is None:
        raise DocumentNotFoundError(document_id)

    return document
