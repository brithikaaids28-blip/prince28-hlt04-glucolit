"""Compare all classifier prompt versions against the evaluation test set."""

import asyncio
import hashlib
import json
from pathlib import Path

from glucolit.config import get_settings
from glucolit.llm.classify import accuracy, classify, find_leaks
from glucolit.llm.gateway import LLMUnavailable, build_gateway
from glucolit.llm.prompts import PROMPTS_DIR, read_prompt, versions

ROOT = Path(__file__).resolve().parents[1]
TESTSET = ROOT / "eval" / "prompt_testset.jsonl"
CACHE_DIR = ROOT / "eval" / "cache"


def load_testset() -> list[dict]:
    """Load and validate the JSONL evaluation questions."""
    rows = []

    with TESTSET.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on test-set line {line_number}: {exc}") from exc

            if not isinstance(row.get("question"), str):
                raise ValueError(f"Missing question on line {line_number}")

            if row.get("label") not in {"docs", "personal", "off_topic"}:
                raise ValueError(f"Invalid label on line {line_number}")

            rows.append(row)

    if not rows:
        raise ValueError("The evaluation test set is empty.")

    return rows


def load_cache(version: str, prompt: str) -> dict:
    """Load cached results, invalidating them if the prompt changes."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    path = CACHE_DIR / f"{version}.json"
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))

        if data.get("prompt_sha256") == prompt_hash:
            return data.get("results", {})

    return {}


def save_cache(version: str, prompt: str, results: dict) -> None:
    """Save results after each question so interrupted runs can resume."""
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    data = {
        "prompt_sha256": prompt_hash,
        "results": results,
    }

    path = CACHE_DIR / f"{version}.json"
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


async def main() -> None:
    testset = load_testset()
    prompt_versions = versions(PROMPTS_DIR, "classify")

    if not prompt_versions:
        raise FileNotFoundError("No classify prompt versions found.")

    questions = [row["question"] for row in testset]
    settings = get_settings()
    gateway = build_gateway(settings)

    if not gateway.providers:
        raise LLMUnavailable("No LLM API keys are configured.")

    print(f"Questions: {len(testset)}")
    print(f"Prompt versions: {', '.join(prompt_versions)}")
    print()

    summaries = []

    for version in prompt_versions:
        prompt = read_prompt(PROMPTS_DIR, version)
        cached = load_cache(version, prompt)

        leaks = find_leaks(prompt, questions)

        if leaks:
            print(f"LEAK: {version} contains {len(leaks)} test question(s).")
            for question in leaks:
                print(f"  {question}")

        print(f"Testing {version}...")

        rows = []
        total_input = 0
        total_output = 0
        total_cost = 0.0
        cache_hits = 0

        for index, item in enumerate(testset, start=1):
            question = item["question"]

            if question in cached:
                result = cached[question]
                cache_hits += 1
            else:
                try:
                    prediction, llm_result = await classify(
                        gateway,
                        prompt,
                        version,
                        question,
                    )
                except Exception as exc:
                    raise RuntimeError(f"Failed on {version}, question {index}: {exc}") from exc

                result = {
                    "got": prediction,
                    "tokens_in": llm_result.tokens_in,
                    "tokens_out": llm_result.tokens_out,
                    "cost_inr": llm_result.cost_inr,
                    "provider": llm_result.provider,
                    "model": llm_result.model,
                }

                cached[question] = result
                save_cache(version, prompt, cached)

            rows.append(
                {
                    "label": item["label"],
                    "got": result["got"],
                }
            )

            total_input += result.get("tokens_in", 0)
            total_output += result.get("tokens_out", 0)
            total_cost += result.get("cost_inr", 0.0)

            print(
                f"  {index:02}/{len(testset)} "
                f"{'CACHE' if question in cached and cache_hits else 'DONE'}"
            )

        correct = sum(row["label"] == row["got"] for row in rows)
        score = accuracy(rows) * 100

        summaries.append(
            {
                "version": version,
                "correct": correct,
                "total": len(rows),
                "accuracy": score,
                "tokens_in": total_input,
                "tokens_out": total_output,
                "cost": total_cost,
                "cache_hits": cache_hits,
                "misses": [
                    {
                        "question": testset[i]["question"],
                        "expected": testset[i]["label"],
                        "got": rows[i]["got"],
                    }
                    for i in range(len(rows))
                    if rows[i]["label"] != rows[i]["got"]
                ],
            }
        )

        print(f"  Accuracy: {correct}/{len(rows)} ({score:.1f}%) | Cache hits: {cache_hits}")
        print()

    print("=" * 78)
    print("PROMPT COMPARISON")
    print("=" * 78)
    print(f"{'Version':<18} {'Accuracy':>10} {'Input':>10} {'Output':>10} {'Cost INR':>12}")

    for item in summaries:
        print(
            f"{item['version']:<18} "
            f"{item['accuracy']:>9.1f}% "
            f"{item['tokens_in']:>10} "
            f"{item['tokens_out']:>10} "
            f"{item['cost']:>12.4f}"
        )

    print()
    print("MISCLASSIFICATIONS")
    print("=" * 78)

    for item in summaries:
        print(f"\n{item['version']}:")
        if not item["misses"]:
            print("  No misclassifications.")
        for miss in item["misses"]:
            print(f"  Expected: {miss['expected']} | Got: {miss['got']}")
            print(f"  Question: {miss['question']}")

    print()
    print(f"Cache directory: {CACHE_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
