from eval_cases import JOB_001
from experiment import ExecutionResult, run_experiment
from models import (
    ActionType,
    DiagnosisCode,
    Finding,
    InvestigationResult,
    RecommendedAction,
)


def valid_result() -> InvestigationResult:
    return InvestigationResult(
        job_id="job-001",
        findings=[
            Finding(
                report_id="report-A",
                diagnosis_code=DiagnosisCode.DELIVERED,
                conclusion="Delivered",
                summary="Sender success and recipient acceptance agree.",
                evidence_ids=["attempt-A-1", "receipt-A-1"],
            ),
            Finding(
                report_id="report-B",
                diagnosis_code=(
                    DiagnosisCode.DELIVERED_WITH_SENDER_STATUS_UNRESOLVED
                ),
                conclusion="Delivered despite sender timeout",
                summary="The receipt conflicts with the sender timeout.",
                evidence_ids=["attempt-B-1", "receipt-B-1"],
            ),
            Finding(
                report_id="report-C",
                diagnosis_code=(
                    DiagnosisCode.DESTINATION_CONFIGURATION_MISSING
                ),
                conclusion="Destination configuration missing",
                summary="The attempt failed because configuration was absent.",
                evidence_ids=["attempt-C-1"],
            ),
        ],
        unresolved_questions=[],
        recommended_actions=[
            RecommendedAction(
                report_id="report-B",
                action_type=ActionType.RECONCILE_SENDER_STATUS,
                action="Reconcile sender status.",
                rationale="The recipient receipt proves delivery.",
            ),
            RecommendedAction(
                report_id="report-C",
                action_type=ActionType.REPAIR_DESTINATION_CONFIGURATION,
                action="Repair destination configuration.",
                rationale="Configuration is missing.",
            ),
        ],
    )


def test_run_experiment_compares_quality_latency_and_usage() -> None:
    baseline_result = valid_result()
    agent_result = valid_result()
    agent_result.findings[0].evidence_ids = ["receipt-A-1"]
    clock_values = iter([10.0, 10.1, 20.0, 20.25])

    report = run_experiment(
        case=JOB_001,
        model="test-model",
        repetitions=1,
        runners={
            "baseline": lambda: ExecutionResult(
                result=baseline_result,
                llm_calls=1,
                tool_calls=0,
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
            ),
            "agent": lambda: ExecutionResult(
                result=agent_result,
                llm_calls=3,
                tool_calls=5,
                input_tokens=300,
                output_tokens=40,
                total_tokens=340,
            ),
        },
        clock=lambda: next(clock_values),
    )

    assert [trial.passed for trial in report.trials] == [True, False]
    assert [trial.latency_ms for trial in report.trials] == [100.0, 250.0]
    assert [trial.stop_reason for trial in report.trials] == [
        "complete",
        "complete",
    ]
    baseline, agent = report.summaries
    assert baseline.pass_rate == 1.0
    assert baseline.average_score == 1.0
    assert baseline.total_tokens == 120
    assert baseline.average_llm_calls == 1.0
    assert agent.pass_rate == 0.0
    assert agent.average_score < 1.0
    assert agent.total_tokens == 340
    assert agent.average_tool_calls == 5.0


def test_run_experiment_records_errors_and_continues() -> None:
    calls = 0

    def failing_runner() -> ExecutionResult:
        nonlocal calls
        calls += 1
        raise RuntimeError("temporary model failure")

    clock_values = iter([0.0, 0.1, 1.0, 1.2])
    report = run_experiment(
        case=JOB_001,
        model="test-model",
        repetitions=2,
        runners={"agent": failing_runner},
        modes=("agent",),
        clock=lambda: next(clock_values),
    )

    assert calls == 2
    assert report.summaries[0].pass_rate == 0.0
    assert report.summaries[0].average_score == 0.0
    assert report.summaries[0].total_tokens is None
    assert all(
        trial.error == "RuntimeError: temporary model failure"
        for trial in report.trials
    )


def test_run_experiment_rejects_invalid_configuration() -> None:
    try:
        run_experiment(
            case=JOB_001,
            model="test-model",
            repetitions=0,
            runners={},
        )
    except ValueError as error:
        assert str(error) == "repetitions must be at least 1"
    else:
        raise AssertionError("Expected invalid repetitions to be rejected")
