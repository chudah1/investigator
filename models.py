from datetime import datetime

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
class Finding(BaseModel):
    report_id: str = Field(description="The report this finding concerns.")
    conclusion: str = Field(description="A concise diagnosis for the report.")
    summary: str = Field(
        description="An evidence-grounded explanation of the diagnosis."
    )
    evidence_ids: list[str] = Field(
        description="IDs of supplied evidence records supporting the finding."
    )


class RecommendedAction(BaseModel):
    report_id: str = Field(description="The report this action concerns.")
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
        description="Questions that cannot be answered from the supplied evidence."
    )
    recommended_actions: list[RecommendedAction] = Field(
        description="Evidence-grounded next actions; omit unnecessary actions."
    )
