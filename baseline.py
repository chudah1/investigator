from typing import Any

from models import InvestigationResult, JobEvidence
from validation import InvestigationValidationError, validate_result


DEFAULT_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """
You investigate failed report deliveries.

Use only the supplied evidence. Do not invent facts or evidence IDs.
Produce exactly one finding for every expected report.
Distinguish a sender's recorded status from confirmed recipient delivery.
When evidence is insufficient or conflicting, state the uncertainty.
Do not recommend retrying a report when a recipient receipt proves delivery.

Evidence IDs may only be IDs that appear in the supplied evidence as a
report_id, attempt_id, receipt_id, or destination_config.destination_id.
""".strip()


def create_openai_client() -> Any:
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError(
            "The OpenAI SDK is not installed. Run: pip install -r requirements.txt"
        ) from error

    return OpenAI()


def investigate_with_openai(
    client: Any,
    evidence: JobEvidence,
    model: str = DEFAULT_MODEL,
) -> InvestigationResult:
    response = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Investigate this job using only the following evidence:\n\n"
                    f"{evidence.model_dump_json(indent=2)}"
                ),
            },
        ],
        text_format=InvestigationResult,
    )

    result = response.output_parsed
    if not isinstance(result, InvestigationResult):
        raise RuntimeError(
            "The model did not return a parsed InvestigationResult. "
            "The response may have been refused or incomplete."
        )

    validate_investigation_result(evidence, result)
    return result


def validate_investigation_result(
    evidence: JobEvidence,
    result: InvestigationResult,
) -> None:
    validate_result(
        result=result,
        job_id=evidence.job.job_id,
        expected_report_ids=set(evidence.job.expected_reports),
        valid_evidence_ids=_collect_valid_evidence_ids(evidence),
    )


def _collect_valid_evidence_ids(evidence: JobEvidence) -> set[str]:
    evidence_ids: set[str] = set()

    for report_evidence in evidence.reports:
        evidence_ids.add(report_evidence.report.report_id)
        evidence_ids.update(
            attempt.attempt_id
            for attempt in report_evidence.delivery_attempts
        )
        evidence_ids.update(
            receipt.receipt_id
            for receipt in report_evidence.recipient_receipts
        )

        if report_evidence.destination_config is not None:
            evidence_ids.add(
                report_evidence.destination_config.destination_id
            )

    return evidence_ids
