import json

from eval_cases import JOB_001
from eval_cli import main
from evaluation import evaluate_result
from investigation_policy import DECISION_POLICY
from baseline import SYSTEM_PROMPT
from investigator_graph import FINALIZER_PROMPT
from models import (
    ActionType,
    DiagnosisCode,
    Finding,
    InvestigationResult,
    RecommendedAction,
)


def correct_result() -> InvestigationResult:
    return InvestigationResult(
        job_id="job-001",
        findings=[
            Finding(
                report_id="report-A",
                diagnosis_code=DiagnosisCode.DELIVERED,
                conclusion="Delivered",
                summary="The recipient accepted the report.",
                evidence_ids=["attempt-A-1", "receipt-A-1"],
            ),
            Finding(
                report_id="report-B",
                diagnosis_code=(
                    DiagnosisCode.DELIVERED_WITH_SENDER_STATUS_UNRESOLVED
                ),
                conclusion="Delivered despite sender timeout",
                summary="The recipient receipt confirms delivery.",
                evidence_ids=["attempt-B-1", "receipt-B-1"],
            ),
            Finding(
                report_id="report-C",
                diagnosis_code=(
                    DiagnosisCode.DESTINATION_CONFIGURATION_MISSING
                ),
                conclusion="Configuration repair required",
                summary="The destination configuration was not found.",
                evidence_ids=["attempt-C-1"],
            ),
        ],
        unresolved_questions=[],
        recommended_actions=[
            RecommendedAction(
                report_id="report-B",
                action_type=ActionType.RECONCILE_SENDER_STATUS,
                action="Reconcile the sender status.",
                rationale="The timeout conflicts with the receipt.",
            ),
            RecommendedAction(
                report_id="report-C",
                action_type=ActionType.REPAIR_DESTINATION_CONFIGURATION,
                action="Repair the destination configuration.",
                rationale="The destination configuration is missing.",
            ),
        ],
    )


def flawed_agent_result() -> InvestigationResult:
    return InvestigationResult(
        job_id="job-001",
        findings=[
            Finding(
                report_id="report-A",
                diagnosis_code=DiagnosisCode.DELIVERED,
                conclusion="Delivered successfully with receipt.",
                summary="The recipient receipt confirmed acceptance.",
                evidence_ids=["attempt-A-1", "receipt-A-1"],
            ),
            Finding(
                report_id="report-B",
                diagnosis_code=DiagnosisCode.DELIVERY_FAILED,
                conclusion="Delivery timed out.",
                summary=(
                    "The recipient did not acknowledge receipt, although a "
                    "receipt record exists."
                ),
                evidence_ids=["attempt-B-1", "receipt-B-1"],
            ),
            Finding(
                report_id="report-C",
                diagnosis_code=(
                    DiagnosisCode.DESTINATION_CONFIGURATION_MISSING
                ),
                conclusion="Delivery failed due to missing configuration.",
                summary="The destination configuration was not found.",
                evidence_ids=["attempt-C-1"],
            ),
        ],
        unresolved_questions=[],
        recommended_actions=[],
    )


def test_correct_result_passes_job_001_eval() -> None:
    report = evaluate_result(correct_result(), JOB_001)

    assert report.passed is True
    assert report.score == 1.0
    assert report.issues == []


def test_baseline_and_agent_share_the_same_decision_policy() -> None:
    assert DECISION_POLICY in SYSTEM_PROMPT
    assert DECISION_POLICY in FINALIZER_PROMPT


def test_eval_catches_observed_agent_failures() -> None:
    report = evaluate_result(flawed_agent_result(), JOB_001)

    assert report.passed is False
    assert {
        (issue.report_id, issue.check) for issue in report.issues
    } >= {
        ("report-B", "diagnosis_code"),
        ("report-B", "contradictory_claim"),
        ("report-B", "required_action"),
        ("report-C", "required_action"),
    }


def test_eval_uses_machine_readable_categories_not_friendly_wording() -> None:
    result = correct_result()
    report_b = next(
        finding
        for finding in result.findings
        if finding.report_id == "report-B"
    )
    report_b.diagnosis_code = DiagnosisCode.DELIVERY_FAILED
    report_b.conclusion = "Delivered despite sender timeout"

    report = evaluate_result(result, JOB_001)

    assert ("report-B", "diagnosis_code") in {
        (issue.report_id, issue.check) for issue in report.issues
    }


def test_eval_requires_all_decisive_evidence() -> None:
    result = correct_result()
    report_a = next(
        finding
        for finding in result.findings
        if finding.report_id == "report-A"
    )
    report_a.evidence_ids = ["receipt-A-1"]

    report = evaluate_result(result, JOB_001)

    assert any(
        issue.report_id == "report-A"
        and issue.check == "required_evidence"
        and "attempt-A-1" in issue.message
        for issue in report.issues
    )


def test_eval_cli_returns_failure_for_failed_result(tmp_path, capsys) -> None:
    result_path = tmp_path / "agent-result.json"
    result_path.write_text(
        json.dumps(flawed_agent_result().model_dump(mode="json")),
        encoding="utf-8",
    )

    exit_code = main([str(result_path)])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["passed"] is False
    assert output["score"] < 1
