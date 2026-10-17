"""Run the eval cases against the live assistant and report the pass rate.

    uv run python evals/run_evals.py                       # all cases
    uv run python evals/run_evals.py --case returns --case cod
    uv run python evals/run_evals.py --cases evals/cases/other_store.json

Needs the store indexed first (python -m app.cli ingest <url>). Each run appends a
line to evals/history.csv so the pass rate can be tracked across prompt changes.
"""

import argparse
import csv
import json
import logging
import subprocess
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

# Run as a script, so make the repo root importable for `app` and `evals`.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.chat import answer  # noqa: E402
from app.config import settings  # noqa: E402
from app.models import Message  # noqa: E402
from evals.checks import check_answer  # noqa: E402

DEFAULT_CASES = ROOT / "evals" / "cases" / "minimalist.json"
HISTORY = ROOT / "evals" / "history.csv"
RESULTS_DIR = ROOT / "evals" / "results"  # full answers per run; gitignored


def run_case(conn, site, case: dict) -> dict:
    history = [Message(**m) for m in case.get("history", [])]
    started = time.time()
    try:
        reply, results = answer(conn, site, case["question"], history, case.get("page_url"))
        failures = check_answer(case, reply, results, site.url)
    except Exception as exc:  # one broken case shouldn't stop the run; record it as a failure
        reply, failures = "", [f"error: {exc}"]
    return {
        "id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "answer": reply,
        "failures": failures,
        "seconds": round(time.time() - started, 2),
    }


def _git_commit() -> str:
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return out.stdout.strip() or "unknown"


def report(outcomes: list[dict]) -> float:
    for o in outcomes:
        mark = "PASS" if not o["failures"] else "FAIL"
        print(f"{mark}  {o['category']:<13} {o['id']:<20} {o['seconds']:>5.1f}s")
        for failure in o["failures"]:
            print(f"      - {failure}")
        if o["failures"]:
            print(f"      answer: {o['answer'].strip()[:300]}")

    by_category: dict[str, list[bool]] = defaultdict(list)
    for o in outcomes:
        by_category[o["category"]].append(not o["failures"])
    print("\nBy category:")
    for category, passes in by_category.items():
        print(f"  {category:<13} {sum(passes)}/{len(passes)}")

    passed = sum(not o["failures"] for o in outcomes)
    rate = passed / len(outcomes) if outcomes else 0.0
    print(f"\nPass rate: {passed}/{len(outcomes)} = {rate:.0%}  (model: {settings.chat_model})")
    return rate


def save(outcomes: list[dict], rate: float, cases_file: Path) -> None:
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / f"{stamp}.json").write_text(json.dumps(outcomes, indent=2, ensure_ascii=False))

    new_file = not HISTORY.exists()
    with HISTORY.open("a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(
                ["timestamp", "commit", "cases_file", "model", "passed", "total", "rate"]
            )
        passed = sum(not o["failures"] for o in outcomes)
        writer.writerow(
            [stamp, _git_commit(), cases_file.name, settings.chat_model, passed, len(outcomes),
             f"{rate:.3f}"]
        )  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser(description="Run assistant evals")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--case", action="append", help="run only these case ids")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    spec = json.loads(args.cases.read_text())
    cases = [c for c in spec["cases"] if not args.case or c["id"] in args.case]
    conn = db.connect()
    site = db.find_site(conn, spec["store_url"])
    if site is None or site.last_crawled_at is None:
        print(
            f"{spec['store_url']} isn't indexed. Run: python -m app.cli ingest {spec['store_url']}"
        )
        return 1

    outcomes = [run_case(conn, site, case) for case in cases]
    rate = report(outcomes)
    # Partial runs (--case) are for debugging; only full runs go into the history.
    if not args.case:
        save(outcomes, rate, args.cases)
    return 0


if __name__ == "__main__":
    sys.exit(main())
