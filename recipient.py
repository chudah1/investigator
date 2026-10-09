from dataclasses import dataclass
from time import sleep
from typing import Literal, Protocol

from fastapi import FastAPI
from pydantic import BaseModel

from repository import Repository


class DeliveryRequest(BaseModel):
    report_id: str
    delivery_key: str


class DeliveryResponse(BaseModel):
    status: Literal["accepted"]
    receipt_id: str


class Acknowledgement(Protocol):
    def wait(self) -> None: ...


@dataclass(frozen=True)
class DelayedAcknowledgement:
    delay_seconds: float

    def wait(self) -> None:
        sleep(self.delay_seconds)


def create_recipient_app(
    repository: Repository,
    acknowledgement: Acknowledgement | None = None,
) -> FastAPI:
    app = FastAPI(title="Report Recipient")

    @app.post(
        "/deliveries",
        response_model=DeliveryResponse,
        status_code=202,
    )
    def accept_delivery(delivery: DeliveryRequest) -> DeliveryResponse:
        receipt = repository.create_recipient_receipt(
            report_id=delivery.report_id,
            delivery_key=delivery.delivery_key,
        )
        if acknowledgement is not None:
            acknowledgement.wait()
        return DeliveryResponse(
            status="accepted",
            receipt_id=receipt.receipt_id,
        )

    return app
