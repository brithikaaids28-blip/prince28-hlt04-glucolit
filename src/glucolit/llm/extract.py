"""Extract and validate structured metadata from research articles."""

import json
import logging

from pydantic import ValidationError

from glucolit.llm.doc_meta import DocMeta
from glucolit.llm.gateway import LLMGateway, LLMResult

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 2


def build_messages(
    prompt: str,
    article_text: str,
    pmcid: str,
) -> list[dict[str, str]]:
    """Build messages with the known PMC identifier."""
    return [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": (
                f"Known PMC identifier: {pmcid}\n\n"
                "Extract metadata from the article below.\n"
                "<article>\n"
                f"{article_text.strip()}\n"
                "</article>"
            ),
        },
    ]


def parse_metadata(reply: str) -> DocMeta:
    """Parse JSON and validate it against the strict DocMeta schema."""
    try:
        data = json.loads(reply)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("The model response must be a JSON object.")

    try:
        return DocMeta.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise ValueError(f"Metadata validation failed: {details}") from exc


async def extract_metadata(
    gateway: LLMGateway,
    prompt: str,
    version: str,
    article_text: str,
    pmcid: str,
) -> tuple[DocMeta, LLMResult]:
    """Extract metadata, retrying invalid model output once."""
    if not article_text.strip():
        raise ValueError("Article text cannot be empty.")

    if not pmcid.startswith("PMC") or not pmcid[3:].isdigit():
        raise ValueError(f"Invalid PMC identifier: {pmcid}")

    messages = build_messages(prompt, article_text, pmcid)
    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            result = await gateway.generate(
                messages,
                purpose="extract",
                prompt_version=version,
                temperature=0,
            )
            metadata = parse_metadata(result.text)

            if metadata.pmcid != pmcid:
                raise ValueError(f"Returned PMCID {metadata.pmcid} does not match {pmcid}")

            return metadata, result

        except ValueError as exc:
            last_error = exc
            log.warning(
                "Metadata extraction attempt %s/%s failed: %s",
                attempt,
                MAX_ATTEMPTS,
                exc,
            )

            if attempt < MAX_ATTEMPTS:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Correct the previous JSON response. "
                            f"Validation problem: {exc}. "
                            "Return one valid JSON object only."
                        ),
                    }
                )

    raise ValueError(f"Metadata extraction failed after {MAX_ATTEMPTS} attempts: {last_error}")
