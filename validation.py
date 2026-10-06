from models import InvestigationResult


class InvestigationValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_result(
    result: InvestigationResult,
    job_id: str,
    expected_report_ids: set[str],
    valid_evidence_ids: set[str],
    require_all_findings: bool = True,
) -> None:
    errors: list[str] = []

    if result.job_id != job_id:
        errors.append(
            f"result job_id {result.job_id!r} does not match "
            f"evidence job_id {job_id!r}"
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

    if require_all_findings:
        missing_finding_ids = sorted(
            expected_report_ids - finding_report_id_set
        )
        if missing_finding_ids:
            errors.append(
                f"missing findings for report IDs: {missing_finding_ids}"
            )

    unexpected_finding_ids = sorted(
        finding_report_id_set - expected_report_ids
    )
    if unexpected_finding_ids:
        errors.append(
            f"findings reference unexpected report IDs: "
            f"{unexpected_finding_ids}"
        )

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
    unexpected_action_ids = sorted(
        action_report_ids - expected_report_ids
    )
    if unexpected_action_ids:
        errors.append(
            f"actions reference unexpected report IDs: "
            f"{unexpected_action_ids}"
        )

    if errors:
        raise InvestigationValidationError(errors)
