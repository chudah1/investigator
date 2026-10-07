from evaluation import EvaluationCase, ReportExpectation
from models import ActionType, DiagnosisCode


JOB_001 = EvaluationCase(
    case_id="job-001-delivery-diagnosis",
    job_id="job-001",
    reports=(
        ReportExpectation(
            report_id="report-A",
            expected_diagnosis_code=DiagnosisCode.DELIVERED,
            required_evidence_ids=frozenset(
                {"attempt-A-1", "receipt-A-1"}
            ),
            forbidden_claims=(
                "without acknowledgment",
                "without acknowledgement",
                "no receipt",
                "not delivered",
            ),
            forbidden_action_types=frozenset({ActionType.RETRY_DELIVERY}),
        ),
        ReportExpectation(
            report_id="report-B",
            expected_diagnosis_code=(
                DiagnosisCode.DELIVERED_WITH_SENDER_STATUS_UNRESOLVED
            ),
            required_evidence_ids=frozenset(
                {"attempt-B-1", "receipt-B-1"}
            ),
            forbidden_claims=(
                "without acknowledgment",
                "without acknowledgement",
                "no acknowledgment",
                "no acknowledgement",
                "did not acknowledge",
                "no receipt",
                "not delivered",
                "delivery failed",
            ),
            action_required=True,
            acceptable_action_types=frozenset(
                {
                    ActionType.RECONCILE_SENDER_STATUS,
                    ActionType.INVESTIGATE,
                }
            ),
            forbidden_action_types=frozenset({ActionType.RETRY_DELIVERY}),
        ),
        ReportExpectation(
            report_id="report-C",
            expected_diagnosis_code=(
                DiagnosisCode.DESTINATION_CONFIGURATION_MISSING
            ),
            required_evidence_ids=frozenset({"attempt-C-1"}),
            action_required=True,
            acceptable_action_types=frozenset(
                {ActionType.REPAIR_DESTINATION_CONFIGURATION}
            ),
        ),
    ),
)


JOB_002 = EvaluationCase(
    case_id="job-002-failure-and-uncertainty",
    job_id="job-002",
    minimum_unresolved_questions=1,
    reports=(
        ReportExpectation(
            report_id="report-D",
            expected_diagnosis_code=DiagnosisCode.DELIVERY_FAILED,
            required_evidence_ids=frozenset({"attempt-D-1"}),
            action_required=True,
            acceptable_action_types=frozenset(
                {ActionType.RETRY_DELIVERY}
            ),
        ),
        ReportExpectation(
            report_id="report-E",
            expected_diagnosis_code=DiagnosisCode.INSUFFICIENT_EVIDENCE,
            required_evidence_ids=frozenset(
                {"report-E", "destination-E"}
            ),
            action_required=True,
            acceptable_action_types=frozenset({ActionType.INVESTIGATE}),
            forbidden_action_types=frozenset(
                {ActionType.RETRY_DELIVERY}
            ),
        ),
    ),
)


SCALE_REPORT_IDS = tuple(
    f"report-scale-{number:02d}" for number in range(1, 7)
)

JOB_003 = EvaluationCase(
    case_id="job-003-multi-report-scale",
    job_id="job-003",
    reports=tuple(
        ReportExpectation(
            report_id=report_id,
            expected_diagnosis_code=DiagnosisCode.DELIVERED,
            required_evidence_ids=frozenset(
                {
                    f"attempt-{report_id.removeprefix('report-')}",
                    f"receipt-{report_id.removeprefix('report-')}",
                }
            ),
            forbidden_claims=("no receipt", "not delivered"),
            forbidden_action_types=frozenset(
                {ActionType.RETRY_DELIVERY}
            ),
        )
        for report_id in SCALE_REPORT_IDS
    ),
)


CASES_BY_JOB_ID = {
    case.job_id: case
    for case in (JOB_001, JOB_002, JOB_003)
}
