"""Load and manage versioned task prompts."""

import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


def versions(directory: Path, task: str) -> list[str]:
    """Return prompt versions sorted by version number."""
    pattern = re.compile(rf"^{re.escape(task)}_v(\d+)\.md$")
    found = []

    for path in directory.glob(f"{task}_v*.md"):
        match = pattern.match(path.name)
        if match:
            found.append((int(match.group(1)), path.stem))

    return [name for _, name in sorted(found)]


def latest(directory: Path, task: str) -> str:
    """Return the newest prompt version name."""
    found = versions(directory, task)

    if not found:
        raise FileNotFoundError(f"No prompt found for task: {task}")

    return found[-1]


def read_prompt(directory: Path, version: str) -> str:
    """Read a prompt and remove surrounding whitespace."""
    path = directory / f"{version}.md"
    return path.read_text(encoding="utf-8").strip()


def load_prompt(task: str) -> tuple[str, str]:
    """Return the newest prompt text and its version name."""
    version = latest(PROMPTS_DIR, task)
    return read_prompt(PROMPTS_DIR, version), version
