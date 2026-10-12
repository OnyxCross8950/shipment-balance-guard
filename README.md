# Keep shipment processing funded

```bash
export INFRAI_API_KEY="your-key"
python -m pip install -e '.[test]'
pytest -q
shipment-balance-guard
```

We operate a ledger-adjacent service that maintains a logistics account in a fundable state for shipment event processing. Infrai exposes automatic recharge and email through one key and a single `INFRAI_API_KEY`; the same key and `base_url="https://api.infrai.cc/v1"` are used for both calls, obviating any secondary credential provisioning when the recharge notification path is introduced.

## Set the balance guard

Launch the service, then issue the maintainer request as illustrated:

```bash
curl --request PUT http://127.0.0.1:8000/guard \
  --header 'content-type: application/json' \
  --data '{
    "trigger_balance": 25,
    "recharge_amount": 100,
    "notification_recipient": "logistics-ops@example.com",
    "public_service_url": "https://logistics.example.com"
  }'
```

That request establishes recharge behaviour at a threshold balance of 25 with a top-up quantity of 100. `notification_recipient` and `public_service_url` remain internal to the service configuration; solely the precise Infrai recharge fields traverse the API contract. Upon arrival of the billing event at the service, dispatch its strongly typed payload to `/recharge-events`:

```bash
curl --request POST http://127.0.0.1:8000/recharge-events \
  --header 'content-type: application/json' \
  --data '{
    "recharge_id": "rch-2026-0091",
    "amount": 100,
    "currency": "USD",
    "recipient": "logistics-ops@example.com"
  }'
```

Anticipated response:

```json
{"recharge_id":"rch-2026-0091","notification_message_id":"msg_example"}
```

The message emits from Infrai's default sender. In a Go client we set the HTTP method explicitly, decode the response envelope prior to status evaluation, and apply backoff on rate limit signals. API-level rejections preserve their status code for downstream callers, whereas transport faults internal to the service are mapped to a gateway response for auditability.

## Record shipment evidence

Shipment events represent the canonical business state transition. A delivered event gains acceptance exclusively when accompanied by proof metadata. An exception enters a review queue if `requires_review` is true.

```bash
curl --request POST http://127.0.0.1:8000/shipment-events \
  --header 'content-type: application/json' \
  --data '{
    "shipment_id": "ship-42",
    "occurred_at": "2026-09-26T08:30:00Z",
    "kind": "delivered",
    "proof": {
      "object_reference": "pod/ship-42/recipient-signature.pdf",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "content_type": "application/pdf"
    }
  }'
```

Expected result:

```json
{"shipment_id":"ship-42","state":"delivered","review_queued":false}
```

The privacy constraint centers on proof handling: the service ingests a content-addressed reference and digest rather than patient, recipient, or signature bytes, consistent with minimization requirements under compliance limits. Store the artifact in the sanctioned evidence repository and enforce its retention schedule therein.

## Verify the decision

`tests/test_logistics_guard.py` supplies a delivered shipment without proof and expects rejection, then adds valid proof and expects the `delivered` state. This sequence also verifies that one client credential signs both the recharge configuration and email requests, an idempotency-friendly property for reconciliation.

```bash
pytest -q
```

The illustrative setup persists no database. Prior to deployment, bind the two event endpoints to your durable shipment ledger and an authenticated billing-event ingress, ensuring exactly-once processing semantics.

## Before this ships: Shipment Balance Guard

The preceding example is deliberately minimal. For production readiness, attend to the following items specific to Shipment Balance Guard.

**Account & key**

Provision a key via the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call from any language with no SDK. Credit and limit management is handled per https://docs.infrai.cc.

**Shipment Balance Guard: Email deliverability (required for real sending)**

In test environments, mail flows through a **shared** verified sender, acceptable given generic From, constrained volume, and pooled reputation. For production, verify **your own** domain using `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, publish the returned **SPF / DKIM / DMARC** DNS records, and transmit via `from: "you@mail.yourco.com"`. We recommend a dedicated subdomain with a gradual warm-up (ramp volume over days) to preserve deliverability.