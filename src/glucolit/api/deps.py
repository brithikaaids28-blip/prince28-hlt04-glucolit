"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Request

from glucolit.store import DocumentStore


def get_store(request: Request) -> DocumentStore:
    """Get the document store from application state."""
    return request.app.state.store


StoreDep = Annotated[DocumentStore, __import__("fastapi").Depends(get_store)]
