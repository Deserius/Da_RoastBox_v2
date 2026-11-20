"""Stripe checkout built directly on the official ``stripe`` SDK.

This replaces the former dependency on ``emergentintegrations.payments.stripe``,
a vendor-specific wrapper that is not on PyPI. Behaviour is equivalent: create a
Checkout Session for the amount, and verify + parse webhook events with the
signing secret.

Design notes
------------
* The account key and webhook secret are read at call time, not import time, so
  the settings console can supply them without a process restart.
* ``STRIPE_TEST_ONLY`` is enforced by the caller before construction.
* Only the Stripe-hosted Checkout page is used, so card data never touches this
  server and no PCI scope is added.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import stripe


@dataclass
class CheckoutSessionRequest:
    """What the route wants to sell."""

    amount: float
    currency: str = "usd"
    success_url: str = ""
    cancel_url: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)
    # Optional single line item. Stripe requires a product name for the customer
    # to see; fall back to a generic label so a bare amount still works.
    name: str = "Da RoastBox credits"
    quantity: int = 1


@dataclass
class CheckoutSessionResponse:
    url: str
    session_id: str
    raw: Any = None


@dataclass
class CheckoutStatus:
    """What the caller needs to know about a Checkout Session right now."""

    payment_status: str
    amount_total: Optional[float] = None
    currency: Optional[str] = None
    raw: Any = None


@dataclass
class WebhookEvent:
    """Normalised view of the events this app cares about."""

    event_id: Optional[str]
    event_type: str
    payment_status: str
    session_id: Optional[str]
    metadata: Dict[str, str]
    amount_usd: Optional[float] = None
    raw: Any = None


class StripeCheckout:
    """Minimal asynchronous facade over the synchronous Stripe SDK."""

    def __init__(self, api_key: str, webhook_secret: Optional[str] = None,
                 webhook_url: Optional[str] = None):
        if not api_key:
            raise ValueError("A Stripe secret key is required")
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        self.webhook_url = webhook_url

    # -- checkout ---------------------------------------------------------
    async def create_checkout_session(self, req: CheckoutSessionRequest) -> CheckoutSessionResponse:
        cents = int(round(float(req.amount) * 100))
        if cents < 50:
            # Stripe refuses anything below its minimum; surface a clear error
            # rather than an opaque 400 from the API.
            raise ValueError(f"Amount {req.amount} is below the Stripe minimum of 0.50")

        product_name = (req.metadata or {}).get("name") or req.name

        def _create():
            return stripe.checkout.Session.create(
                api_key=self.api_key,
                mode="payment",
                line_items=[{
                    "quantity": int(req.quantity),
                    "price_data": {
                        "currency": req.currency,
                        "unit_amount": cents,
                        "product_data": {"name": product_name},
                    },
                }],
                success_url=req.success_url,
                cancel_url=req.cancel_url,
                metadata=dict(req.metadata or {}),
                # Copy the metadata onto the PaymentIntent as well, so a
                # checkout.session.* event and a payment_intent.* event both
                # carry the same purchase identifiers.
                payment_intent_data={"metadata": dict(req.metadata or {})},
                allow_promotion_codes=True,
            )

        session = await asyncio.to_thread(_create)
        return CheckoutSessionResponse(url=session.url, session_id=session.id, raw=session)

    # -- polling ------------------------------------------------------------
    async def get_checkout_status(self, session_id: str) -> CheckoutStatus:
        """Ask Stripe directly for a session's status.

        Used both by the success-page poll (the user is watching) and by the
        background sweep that catches anything paid while nobody was looking
        (no public webhook endpoint in local/dev use). Stripe's own
        ``payment_status`` on the session is "paid"/"unpaid"/"no_payment_required";
        callers compare case-insensitively against "paid".
        """
        def _retrieve():
            return stripe.checkout.Session.retrieve(session_id, api_key=self.api_key)

        session = await asyncio.to_thread(_retrieve)
        get = session.get if hasattr(session, "get") else lambda k, d=None: getattr(session, k, d)
        amount = get("amount_total")
        return CheckoutStatus(
            payment_status=str(get("payment_status") or "unknown"),
            amount_total=(float(amount) / 100.0) if isinstance(amount, (int, float)) else None,
            currency=get("currency"),
            raw=session,
        )

    # -- webhooks ---------------------------------------------------------
    async def handle_webhook(self, payload: bytes, signature: str) -> WebhookEvent:
        """Verify the signature, then normalise the event.

        Raises on an invalid signature so the caller can answer 400.
        """
        if not self.webhook_secret:
            raise ValueError("Webhook secret is not configured")
        if not signature:
            raise ValueError("Missing Stripe-Signature header")

        def _parse():
            return stripe.Webhook.construct_event(
                payload, signature, self.webhook_secret, api_key=self.api_key
            )

        event = await asyncio.to_thread(_parse)
        return self._normalise(event)

    @staticmethod
    def _normalise(event: Any) -> WebhookEvent:
        get = event.get if hasattr(event, "get") else lambda k, d=None: getattr(event, k, d)
        event_type = str(get("type") or "")
        data = get("data") or {}
        obj = data.get("object") if hasattr(data, "get") else None
        obj = obj or {}

        def pick(key, default=None):
            if hasattr(obj, "get"):
                return obj.get(key, default)
            return getattr(obj, key, default)

        session_id = pick("id") if event_type.startswith("checkout.session") else pick("id")
        metadata = pick("metadata") or {}
        if hasattr(metadata, "to_dict"):
            metadata = metadata.to_dict()
        metadata = dict(metadata)

        # checkout.session.completed carries payment_status == "paid" for paid
        # sessions; payment_intent.succeeded means the money actually cleared.
        payment_status = str(pick("payment_status") or "")
        if event_type == "payment_intent.succeeded" or event_type == "checkout.session.async_payment_succeeded":
            payment_status = "paid"

        amount = pick("amount_total")
        amount_usd = (float(amount) / 100.0) if isinstance(amount, (int, float)) else None

        # For payment_intent events the checkout session id lives in metadata.
        if not session_id or event_type.startswith("payment_intent"):
            session_id = metadata.get("checkout_session_id") or pick("id")

        return WebhookEvent(
            event_id=str(get("id") or "") or None,
            event_type=event_type,
            payment_status=payment_status,
            session_id=session_id,
            metadata=metadata,
            amount_usd=amount_usd,
            raw=event,
        )


__all__ = [
    "StripeCheckout",
    "CheckoutSessionRequest",
    "CheckoutSessionResponse",
    "CheckoutStatus",
    "WebhookEvent",
]
