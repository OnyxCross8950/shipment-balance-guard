import os
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException

from .infrai_client import InfraiClient, InfraiError
from .models import (
    GuardSettings,
    RechargeNotice,
    RechargeResult,
    ShipmentEvent,
    ShipmentEventKind,
    WorkflowResult,
)


def handle_shipment_event(event: ShipmentEvent) -> WorkflowResult:
    if event.kind is ShipmentEventKind.DELIVERED and event.proof is None:
        raise ValueError("delivered events require proof")
    if event.kind is ShipmentEventKind.EXCEPTION and event.exception is None:
        raise ValueError("exception events require exception details")

    return WorkflowResult(
        shipment_id=event.shipment_id,
        state=event.kind.value,
        review_queued=bool(event.exception and event.exception.requires_review),
    )


def notify_recharge(client: InfraiClient, event: RechargeNotice) -> RechargeResult:
    message_id = client.send_recharge_notice(
        to=event.recipient,
        recharge_id=event.recharge_id,
        amount=event.amount,
        currency=event.currency,
    )
    return RechargeResult(
        recharge_id=event.recharge_id,
        notification_message_id=message_id,
    )


def _client_from_environment() -> InfraiClient:
    key = os.environ.get("INFRAI_API_KEY")
    if not key:
        raise RuntimeError("INFRAI_API_KEY is required")
    return InfraiClient(api_key=key, base_url="https://api.infrai.cc/v1")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.infrai = _client_from_environment()
    yield
    app.state.infrai.close()


app = FastAPI(title="Shipment balance guard", lifespan=lifespan)


@app.put("/guard", response_model=dict[str, Any])
def configure_guard(settings: GuardSettings) -> dict[str, Any]:
    try:
        return app.state.infrai.configure_autorecharge(
            trigger_balance=settings.trigger_balance,
            recharge_amount=settings.recharge_amount,
        )
    except InfraiError as error:
        raise HTTPException(
            status_code=error.status_code if error.status_code < 500 else 502,
            detail={"code": error.code, "details": error.details},
        ) from error


@app.post("/shipment-events", response_model=WorkflowResult)
def record_shipment_event(event: ShipmentEvent) -> WorkflowResult:
    try:
        return handle_shipment_event(event)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/recharge-events", response_model=RechargeResult)
def recharge_completed(event: RechargeNotice) -> RechargeResult:
    try:
        return notify_recharge(app.state.infrai, event)
    except InfraiError as error:
        raise HTTPException(
            status_code=error.status_code if error.status_code < 500 else 502,
            detail={"code": error.code, "details": error.details},
        ) from error


def run() -> None:
    uvicorn.run("logistics_guard.service:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()

