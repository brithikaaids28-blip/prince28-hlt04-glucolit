"""Load and provide access to document records."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DocumentStore:
    def __init__(self, data_file: Path) -> None:
        self.data_file = data_file
        self.records: list[dict[str, Any]] = []

    def load(self) -> None:
        """Load records from the JSON file."""
        with self.data_file.open(encoding="utf-8") as file:
            self.records = json.load(file)

        logger.info(
            "records loaded",
            extra={"records": len(self.records)},
        )

    def list_documents(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return documents up to the requested limit."""
        return self.records[:limit]

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        """Find one document by ID."""
        for record in self.records:
            if record.get("id") == document_id:
                return record

        return None
