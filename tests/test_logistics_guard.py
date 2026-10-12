from typing import Any

import httpx
import pytest

from logistics_guard.infrai_client import InfraiClient, InfraiError
from logistics_guard.models import DeliveryProof, ShipmentEvent, ShipmentEventKind
from logistics_guard.service import handle_shipment_event


def test_delivered_shipment_requires_proof() -> None:
    event = ShipmentEvent(
        shipment_id="ship-42",
        occurred_at="2026-09-26T08:30:00Z",
        kind=ShipmentEventKind.DELIVERED,
    )

    with pytest.raises(ValueError, match="delivered events require proof"):
        handle_shipment_event(event)

    accepted = handle_shipment_event(
        event.model_copy(
            update={
                "proof": DeliveryProof(
                    object_reference="pod/ship-42/recipient-signature.pdf",
                    sha256="a" * 64,
                    content_type="application/pdf",
                )
            }
        )
    )
    assert accepted.state == "delivered"
    assert accepted.review_queued is False


def test_one_client_configures_guard_and_sends_notice() -> None:
    requests: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/account/autorecharge/configure"):
            return httpx.Response(200, json={"ok": True, "data": {"enabled": True}})
        return httpx.Response(200, json={"ok": True, "data": {"message_id": "msg-7"}})

    client = InfraiClient(
        api_key="test-key",
        transport=httpx.MockTransport(responder),
        sleep=lambda _: None,
    )
    configured = client.configure_autorecharge(25.0, 100.0)
    message_id = client.send_recharge_notice("ops@example.com", "rch-7", 100.0, "USD")
    client.close()

    assert configured == {"enabled": True}
    assert message_id == "msg-7"
    assert [request.method for request in requests] == ["PUT", "POST"]
    assert len({request.headers["Authorization"] for request in requests}) == 1


def test_business_rejection_is_decoded_before_status() -> None:
    def responder(_: httpx.Request) -> httpx.Response:
        payload: dict[str, Any] = {
            "ok": False,
            "data": None,
            "error": {"code": "INVALID_ARGUMENT", "message": "amount must be positive"},
            "metadata": {},
        }
        return httpx.Response(400, json=payload)

    client = InfraiClient(api_key="test-key", transport=httpx.MockTransport(responder))
    with pytest.raises(InfraiError) as caught:
        client.configure_autorecharge(25.0, -1.0)
    client.close()

    assert caught.value.code == "INVALID_ARGUMENT"
    assert caught.value.status_code == 400

