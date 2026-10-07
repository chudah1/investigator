from dataclasses import dataclass

from pydantic import BaseModel

from models import ActionType, DiagnosisCode, InvestigationResult


@dataclass(frozen=True)
class ReportExpectation:
    report_id: str
    expected_diagnosis_code: DiagnosisCode
    required_evidence_ids: frozenset[str] = frozenset()
    forbidden_claims: tuple[str, ...] = ()
    action_required: bool = False
    acceptable_action_types: frozenset[ActionType] = frozenset()
    forbidden_action_types: frozenset[ActionType] = frozenset()


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    job_id: str
    reports: tuple[ReportExpectation, ...]
    minimum_unresolved_questions: int = 0


class EvaluationIssue(BaseModel):
    check: str
    message: str
    report_id: str | None = None


class EvaluationReport(BaseModel):
    case_id: str
    passed: bool
    score: float
    passed_checks: int
    total_checks: int
    issues: list[EvaluationIssue]


def evaluate_result(
    result: InvestigationResult,
    case: EvaluationCase,
) -> EvaluationReport:
    total_checks = 0
    passed_checks = 0
    issues: list[EvaluationIssue] = []

    def check(
        passed: bool,
        name: str,
        message: str,
        report_id: str | None = None,
    ) -> None:
        nonlocal total_checks, passed_checks
        total_checks += 1
        if passed:
            passed_checks += 1
            return
        issues.append(
            EvaluationIssue(
                check=name,
                message=message,
                report_id=report_id,
            )
        )

    check(
        result.job_id == case.job_id,
        "job_id",
        f"Expected job {case.job_id!r}, got {result.job_id!r}.",
    )

    expected_report_ids = {report.report_id for report in case.reports}
    actual_report_ids = [finding.report_id for finding in result.findings]
    unexpected_report_ids = sorted(
        set(actual_report_ids) - expected_report_ids
    )
    check(
        not unexpected_report_ids,
        "unexpected_findings",
        f"Unexpected findings: {unexpected_report_ids}.",
    )

    if case.minimum_unresolved_questions:
        check(
            len(result.unresolved_questions)
            >= case.minimum_unresolved_questions,
            "unresolved_questions",
            "Expected at least "
            f"{case.minimum_unresolved_questions} unresolved question(s), "
            f"got {len(result.unresolved_questions)}.",
        )

    actions_by_report = {
        report_id: [
            action
            for action in result.recommended_actions
            if action.report_id == report_id
        ]
        for report_id in expected_report_ids
    }

    for expectation in case.reports:
        findings = [
            finding
            for finding in result.findings
            if finding.report_id == expectation.report_id
        ]
        check(
            len(findings) == 1,
            "finding_count",
            "Expected exactly one finding, "
            f"found {len(findings)}.",
            expectation.report_id,
        )
        if len(findings) != 1:
            continue

        finding = findings[0]
        check(
            finding.diagnosis_code == expectation.expected_diagnosis_code,
            "diagnosis_code",
            "Expected diagnosis code "
            f"{expectation.expected_diagnosis_code.value!r}, got "
            f"{finding.diagnosis_code.value!r}.",
            expectation.report_id,
        )

        missing_evidence = sorted(
            expectation.required_evidence_ids - set(finding.evidence_ids)
        )
        check(
            not missing_evidence,
            "required_evidence",
            f"Missing required evidence IDs: {missing_evidence}.",
            expectation.report_id,
        )

        finding_text = f"{finding.conclusion} {finding.summary}"
        if expectation.forbidden_claims:
            contradictory_claims = [
                phrase
                for phrase in expectation.forbidden_claims
                if _contains_phrase(finding_text, phrase)
            ]
            check(
                not contradictory_claims,
                "contradictory_claim",
                "Finding contains contradictory claims: "
                f"{contradictory_claims}.",
                expectation.report_id,
            )

        actions = actions_by_report[expectation.report_id]
        if expectation.action_required:
            check(
                bool(actions),
                "required_action",
                "Expected a recommended action for this report.",
                expectation.report_id,
            )

        if actions:
            action_types = {action.action_type for action in actions}
            if expectation.acceptable_action_types:
                check(
                    bool(
                        action_types & expectation.acceptable_action_types
                    ),
                    "acceptable_action_type",
                    "Expected at least one action type from "
                    f"{sorted(
                        action_type.value
                        for action_type in expectation.acceptable_action_types
                    )}, got "
                    f"{sorted(
                        action_type.value for action_type in action_types
                    )}.",
                    expectation.report_id,
                )

            if expectation.forbidden_action_types:
                unsafe_actions = sorted(
                    action_type.value
                    for action_type in (
                        action_types & expectation.forbidden_action_types
                    )
                )
                check(
                    not unsafe_actions,
                    "forbidden_action_type",
                    f"Recommended unsafe action types: {unsafe_actions}.",
                    expectation.report_id,
                )

    score = passed_checks / total_checks if total_checks else 0.0
    return EvaluationReport(
        case_id=case.case_id,
        passed=not issues,
        score=round(score, 3),
        passed_checks=passed_checks,
        total_checks=total_checks,
        issues=issues,
    )


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = " ".join(text.casefold().split())
    normalized_phrase = " ".join(phrase.casefold().split())
    return normalized_phrase in normalized_text
