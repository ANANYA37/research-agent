"""Evaluation harness for generated research reports.

Usage:
    python evaluate.py eval/golden_set.json
"""

import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from agent import run_research
from citations import verify_citations


WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(WORD_RE.findall((text or "").lower()))


def score_report(report: str, reference: str, sources: list[dict]) -> dict:
    report_tokens = _tokens(report)
    reference_tokens = _tokens(reference)
    overlap = report_tokens & reference_tokens

    precision = len(overlap) / max(len(report_tokens), 1)
    recall = len(overlap) / max(len(reference_tokens), 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    citation = verify_citations(report, sources)

    return {
        "lexical_precision": round(precision, 4),
        "lexical_recall": round(recall, 4),
        "lexical_f1": round(f1, 4),
        "citation_valid": citation["valid"],
        "invalid_citations": citation["invalid_references"],
        "overall": round((f1 * 0.8) + ((1.0 if citation["valid"] else 0.0) * 0.2), 4),
    }


async def run_eval(golden_path: Path, output_path: Path) -> dict:
    cases = json.loads(golden_path.read_text(encoding="utf-8"))
    results = []

    for case in cases:
        topic = case["topic"]
        depth = int(case.get("depth", 2))
        reference = case.get("reference_report", "")
        generated = await run_research(topic, depth)
        scores = score_report(generated["report"], reference, generated.get("sources", []))
        results.append({"topic": topic, "depth": depth, "scores": scores})

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cases": results,
        "average_overall": round(
            sum(item["scores"]["overall"] for item in results) / max(len(results), 1),
            4,
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("golden_set", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval") / "latest_results.json",
    )
    args = parser.parse_args()

    summary = asyncio.run(run_eval(args.golden_set, args.output))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

