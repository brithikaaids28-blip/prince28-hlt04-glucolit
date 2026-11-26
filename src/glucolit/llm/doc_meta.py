"""Validated metadata schema for GlucoLit documents."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocMeta(BaseModel):
    """Structured metadata extracted from a diabetes research article."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Five common metadata fields
    doc_kind: Literal[
        "research_article",
        "review",
        "guideline",
        "clinical_trial",
        "case_report",
        "other",
    ]
    year: int | None = Field(default=None, ge=1900, le=2100)
    language: str = Field(min_length=2, max_length=50)
    summary: str = Field(min_length=10, max_length=2000)
    topics: list[str] = Field(min_length=1, max_length=20)

    # Five project-specific fields
    pmcid: str = Field(pattern=r"^PMC\d+$")
    journal: str = Field(min_length=2, max_length=200)
    study_type: str = Field(min_length=2, max_length=150)
    population: str = Field(min_length=5, max_length=1000)
    sample_size: int | None = Field(default=None, ge=1)
