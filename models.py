from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Job(BaseModel):
    job_id: str
    expected_reports: list[str]


class Report(BaseModel):
    report_id: str
    job_id: str
    destination_id: str
    delivery_status: str


class DeliveryAttempt(BaseModel):
    attempt_id: str
    report_id: str
    timestamp: datetime
    outcome: str
    error: str | None = None


class RecipientReceipt(BaseModel):
    receipt_id: str
    report_id: str
    delivery_key: str
    receipt_timestamp: datetime


class DestinationConfig(BaseModel):
    destination_id: str
    endpoint_url: str
    enabled: bool = True


class ReportEvidence(BaseModel):
    report: Report
    delivery_attempts: list[DeliveryAttempt]
    recipient_receipts: list[RecipientReceipt]
    destination_config: DestinationConfig | None


class JobEvidence(BaseModel):
    job: Job
    reports: list[ReportEvidence]


# for the model/agent
class DiagnosisCode(str, Enum):
    DELIVERED = "delivered"
    DELIVERED_WITH_SENDER_STATUS_UNRESOLVED = (
        "delivered_with_sender_status_unresolved"
    )
    DESTINATION_CONFIGURATION_MISSING = (
        "destination_configuration_missing"
    )
    DELIVERY_FAILED = "delivery_failed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ActionType(str, Enum):
    RECONCILE_SENDER_STATUS = "reconcile_sender_status"
    REPAIR_DESTINATION_CONFIGURATION = (
        "repair_destination_configuration"
    )
    RETRY_DELIVERY = "retry_delivery"
    INVESTIGATE = "investigate"


class Finding(BaseModel):
    report_id: str = Field(description="The report this finding concerns.")
    diagnosis_code: DiagnosisCode = Field(
        description="The machine-readable diagnosis supported by the evidence."
    )
    conclusion: str = Field(description="A concise diagnosis for the report.")
    summary: str = Field(
        description="An evidence-grounded explanation of the diagnosis."
    )
    evidence_ids: list[str] = Field(
        description=(
            "IDs of every supplied evidence record directly supporting the "
            "finding's factual claims. Include all decisive records, not only "
            "one sufficient record."
        )
    )


class RecommendedAction(BaseModel):
    report_id: str = Field(description="The report this action concerns.")
    action_type: ActionType = Field(
        description="The machine-readable category of the recommended action."
    )
    action: str = Field(description="The next action to take.")
    rationale: str = Field(
        description="Why the supplied evidence supports this action."
    )


class InvestigationResult(BaseModel):
    job_id: str = Field(description="The investigated job ID.")
    findings: list[Finding] = Field(
        description="Exactly one finding for every expected report."
    )
    unresolved_questions: list[str] = Field(
        description=(
            "Questions that cannot be answered from the supplied evidence. "
            "Identify the affected report ID in each question."
        )
    )
    recommended_actions: list[RecommendedAction] = Field(
        description=(
            "Evidence-grounded next actions. Include an action for each "
            "finding that requires follow-up; omit only resolved findings."
        )
    )
