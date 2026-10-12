from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class ShipmentEventKind(StrEnum):
    ACCEPTED = "accepted"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    EXCEPTION = "exception"


class DeliveryProof(BaseModel):
    object_reference: str = Field(min_length=1, max_length=240)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_type: str = Field(pattern=r"^(image/(jpeg|png)|application/pdf)$")


class ShipmentException(BaseModel):
    code: str = Field(min_length=1, max_length=48)
    summary: str = Field(min_length=1, max_length=240)
    requires_review: bool = True


class ShipmentEvent(BaseModel):
    shipment_id: str = Field(min_length=1, max_length=80)
    occurred_at: datetime
    kind: ShipmentEventKind
    proof: DeliveryProof | None = None
    exception: ShipmentException | None = None


class RechargeNotice(BaseModel):
    recharge_id: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    recipient: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class GuardSettings(BaseModel):
    trigger_balance: float = Field(gt=0)
    recharge_amount: float = Field(gt=0)
    notification_recipient: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    public_service_url: HttpUrl


class WorkflowResult(BaseModel):
    shipment_id: str
    state: str
    review_queued: bool


class RechargeResult(BaseModel):
    recharge_id: str
    notification_message_id: str

