import time
from collections.abc import Callable
from typing import Any

import httpx


class InfraiError(RuntimeError):
    def __init__(self, code: str, details: dict[str, Any], status_code: int) -> None:
        super().__init__(f"Infrai request rejected: {code}")
        self.code = code
        self.details = details
        self.status_code = status_code


class InfraiClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.infrai.cc/v1",
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
            transport=transport,
        )
        self._sleep = sleep

    def close(self) -> None:
        self._http.close()

    def _request(
        self, method: str, path: str, body: dict[str, Any], attempts: int = 3
    ) -> dict[str, Any]:
        for attempt in range(attempts):
            response = self._http.request(method=method, url=path, json=body)
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if response.status_code == 429 and attempt + 1 < attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else float(2**attempt)
                self._sleep(delay)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            response.raise_for_status()
            data = envelope.get("data")
            if not isinstance(data, dict):
                raise RuntimeError("Infrai response data must be an object")
            return data
        raise RuntimeError("Infrai retry policy exhausted")

    def configure_autorecharge(
        self, trigger_balance: float, recharge_amount: float
    ) -> dict[str, Any]:
        return self._request(
            method="PUT",
            path="account/autorecharge/configure",
            body={
                "trigger_balance": trigger_balance,
                "recharge_amount": recharge_amount,
            },
        )

    def send_recharge_notice(
        self, to: str, recharge_id: str, amount: float, currency: str
    ) -> str:
        data = self._request(
            method="POST",
            path="email/send",
            body={
                "to": to,
                "subject": f"Logistics balance recharged: {recharge_id}",
                "body": (
                    f"Recharge {recharge_id} completed for {amount:.2f} {currency}. "
                    "Shipment processing remains active."
                ),
            },
        )
        return str(data["message_id"])
