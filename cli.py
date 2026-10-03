import argparse
from pathlib import Path

from baseline import create_openai_client, investigate_with_openai
from database import Database
from evidence import collect_job_evidence
from repository import Repository


DEFAULT_DB_PATH = Path(__file__).with_name("investigator.db")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Investigate a report-delivery job using collected evidence."
    )
    parser.add_argument(
        "job_id",
        nargs="?",
        default="job-001",
        help="Job to investigate (default: job-001).",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path (default: {DEFAULT_DB_PATH}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    database = Database(str(args.db))
    database.initialize()
    repository = Repository(database)

    evidence = collect_job_evidence(repository, args.job_id)
    if evidence is None:
        print(f"Job not found: {args.job_id}")
        return 1

    client = create_openai_client()
    result = investigate_with_openai(client, evidence)
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
