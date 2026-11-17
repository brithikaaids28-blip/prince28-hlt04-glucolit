"""FastAPI application factory."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from glucolit.api.errors import (
    DocumentNotFoundError,
    document_not_found_handler,
    validation_exception_handler,
)
from glucolit.api.middleware import RequestMiddleware
from glucolit.api.routes import documents, health
from glucolit.config import Settings, get_settings
from glucolit.logging_setup import setup_logging
from glucolit.store import DocumentStore

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = DocumentStore(settings.data_file)
        app.state.store = store
        app.state.records_loaded = False

        try:
            store.load()
            app.state.records_loaded = True
        except FileNotFoundError:
            logger.warning("data file not found")

        yield

    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )

    app.add_middleware(RequestMiddleware)

    app.add_exception_handler(
        DocumentNotFoundError,
        document_not_found_handler,
    )
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )

    app.include_router(health.router)
    app.include_router(documents.router)

    return app
