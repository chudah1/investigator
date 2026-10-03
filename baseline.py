from typing import Any

from models import InvestigationResult, JobEvidence


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


class InvestigationValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


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
    errors: list[str] = []
    expected_report_ids = set(evidence.job.expected_reports)

    if result.job_id != evidence.job.job_id:
        errors.append(
            f"result job_id {result.job_id!r} does not match "
            f"evidence job_id {evidence.job.job_id!r}"
        )

    finding_report_ids = [finding.report_id for finding in result.findings]
    finding_report_id_set = set(finding_report_ids)

    duplicate_finding_ids = sorted(
        {
            report_id
            for report_id in finding_report_ids
            if finding_report_ids.count(report_id) > 1
        }
    )
    if duplicate_finding_ids:
        errors.append(
            f"duplicate findings for report IDs: {duplicate_finding_ids}"
        )

    missing_finding_ids = sorted(expected_report_ids - finding_report_id_set)
    if missing_finding_ids:
        errors.append(
            f"missing findings for report IDs: {missing_finding_ids}"
        )

    unexpected_finding_ids = sorted(finding_report_id_set - expected_report_ids)
    if unexpected_finding_ids:
        errors.append(
            f"findings reference unexpected report IDs: {unexpected_finding_ids}"
        )

    valid_evidence_ids = _collect_valid_evidence_ids(evidence)
    cited_evidence_ids = {
        evidence_id
        for finding in result.findings
        for evidence_id in finding.evidence_ids
    }
    unknown_evidence_ids = sorted(cited_evidence_ids - valid_evidence_ids)
    if unknown_evidence_ids:
        errors.append(f"unknown evidence IDs cited: {unknown_evidence_ids}")

    action_report_ids = {
        action.report_id for action in result.recommended_actions
    }
    unexpected_action_ids = sorted(action_report_ids - expected_report_ids)
    if unexpected_action_ids:
        errors.append(
            f"actions reference unexpected report IDs: {unexpected_action_ids}"
        )

    if errors:
        raise InvestigationValidationError(errors)


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
