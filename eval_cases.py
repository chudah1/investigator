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


CASES_BY_JOB_ID = {JOB_001.job_id: JOB_001}
