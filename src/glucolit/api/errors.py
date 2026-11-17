"""API error handlers."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class DocumentNotFoundError(Exception):
    def __init__(self, document_id: str):
        self.document_id = document_id
        super().__init__(f"Document {document_id} not found")


async def document_not_found_handler(
    request: Request,
    exc: DocumentNotFoundError,
):
    return JSONResponse(
        status_code=404,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": "Not Found",
            "status": 404,
            "detail": str(exc),
            "request_id": getattr(request.state, "request_id", None),
        },
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    errors = []

    for error in exc.errors():
        field = ".".join(str(item) for item in error["loc"])
        errors.append(
            {
                "field": field,
                "message": error["msg"],
            }
        )

    return JSONResponse(
        status_code=422,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": "Validation Error",
            "status": 422,
            "errors": errors,
            "request_id": getattr(request.state, "request_id", None),
        },
    )
