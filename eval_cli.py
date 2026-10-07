import argparse
from pathlib import Path
from typing import Sequence

from eval_cases import CASES_BY_JOB_ID
from evaluation import evaluate_result
from models import InvestigationResult


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate a saved investigation result."
    )
    parser.add_argument(
        "result",
        type=Path,
        help="Path to an InvestigationResult JSON file.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = InvestigationResult.model_validate_json(
        args.result.read_text(encoding="utf-8")
    )
    case = CASES_BY_JOB_ID.get(result.job_id)
    if case is None:
        print(f"No evaluation case for job: {result.job_id}")
        return 2

    report = evaluate_result(result, case)
    print(report.model_dump_json(indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
