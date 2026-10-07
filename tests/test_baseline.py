from types import SimpleNamespace
from typing import Any

import pytest

from baseline import (
    InvestigationValidationError,
    investigate_with_openai,
    validate_investigation_result,
)
from database import Database
from evidence import collect_job_evidence
from models import (
    ActionType,
    DiagnosisCode,
    Finding,
    InvestigationResult,
    JobEvidence,
    RecommendedAction,
)
from repository import Repository
from seed import seed_database


class FakeResponses:
    def __init__(self, output_parsed: object) -> None:
        self.output_parsed = output_parsed
        self.request: dict[str, Any] | None = None

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.request = kwargs
        return SimpleNamespace(output_parsed=self.output_parsed)


class FakeOpenAI:
    def __init__(self, output_parsed: object) -> None:
        self.responses = FakeResponses(output_parsed)


@pytest.fixture
def evidence(tmp_path) -> JobEvidence:
    db_path = tmp_path / "investigator.db"
    seed_database(db_path)
    repository = Repository(Database(str(db_path)))
    collected = collect_job_evidence(repository, "job-001")
    assert collected is not None
    return collected


@pytest.fixture
def valid_result() -> InvestigationResult:
    return InvestigationResult(
        job_id="job-001",
        findings=[
            Finding(
                report_id="report-A",
                diagnosis_code=DiagnosisCode.DELIVERED,
                conclusion="delivered",
                summary="The attempt succeeded and the recipient recorded a receipt.",
                evidence_ids=["report-A", "attempt-A-1", "receipt-A-1"],
            ),
            Finding(
                report_id="report-B",
                diagnosis_code=(
                    DiagnosisCode.DELIVERED_WITH_SENDER_STATUS_UNRESOLVED
                ),
                conclusion="delivered_with_unresolved_sender_status",
                summary="The sender timed out, but the recipient recorded a receipt.",
                evidence_ids=["report-B", "attempt-B-1", "receipt-B-1"],
            ),
            Finding(
                report_id="report-C",
                diagnosis_code=(
                    DiagnosisCode.DESTINATION_CONFIGURATION_MISSING
                ),
                conclusion="configuration_repair_required",
                summary="The attempt failed because destination configuration was absent.",
                evidence_ids=["report-C", "attempt-C-1"],
            ),
        ],
        unresolved_questions=[],
        recommended_actions=[
            RecommendedAction(
                report_id="report-B",
                action_type=ActionType.RECONCILE_SENDER_STATUS,
                action="reconcile_sender_status",
                rationale="The receipt proves delivery, so retrying risks duplication.",
            ),
            RecommendedAction(
                report_id="report-C",
                action_type=ActionType.REPAIR_DESTINATION_CONFIGURATION,
                action="repair_destination_configuration",
                rationale="No destination configuration is available.",
            ),
        ],
    )


def test_investigate_uses_responses_structured_output(
    evidence: JobEvidence,
    valid_result: InvestigationResult,
) -> None:
    client = FakeOpenAI(valid_result)

    result = investigate_with_openai(client, evidence, model="test-model")

    assert result == valid_result
    assert client.responses.request is not None
    assert client.responses.request["model"] == "test-model"
    assert client.responses.request["text_format"] is InvestigationResult
    assert '"report-B"' in client.responses.request["input"][1]["content"]


def test_investigate_rejects_missing_parsed_output(
    evidence: JobEvidence,
) -> None:
    client = FakeOpenAI(None)

    with pytest.raises(RuntimeError, match="parsed InvestigationResult"):
        investigate_with_openai(client, evidence)


def test_semantic_validation_rejects_unknown_evidence_id(
    evidence: JobEvidence,
    valid_result: InvestigationResult,
) -> None:
    invalid_result = valid_result.model_copy(deep=True)
    invalid_result.findings[0].evidence_ids.append("invented-evidence")

    with pytest.raises(
        InvestigationValidationError,
        match="unknown evidence IDs cited",
    ):
        validate_investigation_result(evidence, invalid_result)


def test_semantic_validation_requires_one_finding_per_expected_report(
    evidence: JobEvidence,
    valid_result: InvestigationResult,
) -> None:
    invalid_result = valid_result.model_copy(deep=True)
    invalid_result.findings.pop()

    with pytest.raises(
        InvestigationValidationError,
        match=r"missing findings for report IDs: \['report-C'\]",
    ):
        validate_investigation_result(evidence, invalid_result)


def test_semantic_validation_rejects_action_for_another_report(
    evidence: JobEvidence,
    valid_result: InvestigationResult,
) -> None:
    invalid_result = valid_result.model_copy(deep=True)
    invalid_result.recommended_actions[0].report_id = "report-X"

    with pytest.raises(
        InvestigationValidationError,
        match="actions reference unexpected report IDs",
    ):
        validate_investigation_result(evidence, invalid_result)
