from datetime import datetime

from pydantic import BaseModel


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
