"""Stripe checkout + entitlements engine for Da RoastBox.

Architecture:
  • Credit Packs (one-time, credits never expire)
  • One-time Add-ons (persona/voice/feature unlocks, lifetime founder)
  • Plus & VIP one-time 30-day passes (credits + perks; no auto-renewal)

Server-authoritative pricing. Idempotent purchase application.
"""
import logging
import math
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlsplit
import certifi
import stripe
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError
from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout, CheckoutSessionRequest
)

from auth_deps import get_current_user, active_plan_tier
from models import User, PaymentTransaction, CreditTransaction
from db import users_collection, payments_collection, credits_collection, roasts_collection
from config import STRIPE_TEST_ONLY, APP_BASE_URL
from services.runtime_settings import secret_cached
from services.pricing import PRODUCT_CATALOG, ROAST_COSTS, VIP_CREDIT_DISCOUNT, compute_roast_cost  # noqa: F401
from services.roast_engine import VISIBLE_BILLING

log = logging.getLogger(__name__)
# Stripe's bundled CA file can't verify the Emergent Stripe proxy; use the system/certifi bundle.
stripe.ca_bundle_path = certifi.where()
router = APIRouter(prefix="/payments", tags=["payments"])

class CheckoutRequest(BaseModel):
    pack_id: str
    origin_url: str


def _sdk_safe_amount(amount: float) -> float:
    """Compensate for the upstream SDK truncating float * 100 to integer cents."""
    cents = int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    adjusted = cents / 100
    if int(adjusted * 100) != cents:
        adjusted = math.nextafter(adjusted, math.inf)
    return adjusted


def _checkout_origin(value: str, request_origin: str | None) -> str:
    """Accept only a safe origin, optionally pinned to the deployed frontend."""
    value = value.strip().rstrip("/")
    try:
        parsed = urlsplit(value)
        _ = parsed.port  # validate malformed ports
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid checkout return origin")
    if (parsed.scheme not in ("https", "http") or not parsed.hostname or
            parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
        raise HTTPException(status_code=400, detail="Invalid checkout return origin")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise HTTPException(status_code=400, detail="Checkout return origin must use HTTPS")
    if APP_BASE_URL and value != APP_BASE_URL:
        raise HTTPException(status_code=400, detail="Checkout return origin does not match APP_BASE_URL")
    if request_origin and value != request_origin.rstrip("/"):
        raise HTTPException(status_code=400, detail="Checkout return origin does not match the requesting app")
    return value


def _checkout(host_url: str | None = None) -> StripeCheckout:
    stripe_key = secret_cached("STRIPE_API_KEY")
    if not stripe_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured. Add STRIPE_API_KEY to the backend environment.")
    if STRIPE_TEST_ONLY and not stripe_key.startswith(("sk_test_", "rk_test_")):
        raise HTTPException(status_code=503, detail="Stripe test-only mode requires a test secret key.")
    return StripeCheckout(api_key=stripe_key,
                          webhook_secret=secret_cached("STRIPE_WEBHOOK_SECRET") or None,
                          webhook_url=host_url)


@router.get("/packs")
async def list_packs():
    return {
        "packs": [{"id": k, **v} for k, v in PRODUCT_CATALOG.items()],
        "roast_costs": ROAST_COSTS,
    }


@router.get("/activity")
async def account_activity(response: Response, current_user: User = Depends(get_current_user)):
    """Return only this account's recent stored purchases, credit events and shows.

    No Stripe request is made; status is the app's most recently stored status.
    Never expose provider session IDs, user IDs, transcripts, notes or photos.
    """
    response.headers["Cache-Control"] = "private, no-store"
    owner = {"user_id": current_user.id}
    limit = 20
    payments = await payments_collection.find(owner, {
        "_id": 0, "id": 1, "pack_id": 1, "amount_usd": 1, "credits": 1,
        "payment_status": 1, "created_at": 1,
    }).sort("created_at", -1).limit(limit).to_list(length=limit)
    for payment in payments:
        product = PRODUCT_CATALOG.get(payment.get("pack_id")) or {}
        payment["product_name"] = product.get("name") or "Purchase"
    credit_events = await credits_collection.find(owner, {
        "_id": 0, "id": 1, "amount": 1, "type": 1, "description": 1, "created_at": 1,
    }).sort("created_at", -1).limit(limit).to_list(length=limit)
    shows = await roasts_collection.find({**owner, "billing_state": VISIBLE_BILLING}, {
        "_id": 0, "id": 1, "mode": 1, "subject_name": 1, "credits_spent": 1,
        "was_free_roast": 1, "created_at": 1,
    }).sort("created_at", -1).limit(limit).to_list(length=limit)
    return {"payments": payments, "credit_activity": credit_events, "shows": shows, "limit": limit}


@router.post("/checkout")
async def create_checkout(body: CheckoutRequest, request: Request, current_user: User = Depends(get_current_user)):
    if current_user.is_preview:
        raise HTTPException(status_code=403, detail="Preview accounts cannot make purchases. Sign in with a verified account for checkout.")
    pack = PRODUCT_CATALOG.get(body.pack_id)
    if not pack:
        raise HTTPException(status_code=400, detail="Invalid pack")
    if pack["type"] == "plus_subscription" and current_user.plan_tier == "vip":
        raise HTTPException(status_code=400, detail="Your active VIP pass already includes Plus. Choose VIP to extend it.")
    if not secret_cached("STRIPE_API_KEY") or not secret_cached("STRIPE_WEBHOOK_SECRET"):
        raise HTTPException(status_code=503, detail="Stripe checkout requires both STRIPE_API_KEY and STRIPE_WEBHOOK_SECRET on the server.")

    # VIP gets 10% off credit packs
    amount = pack["amount_usd"]
    if pack["type"] == "credits" and current_user.plan_tier == "vip":
        amount = round(amount * VIP_CREDIT_DISCOUNT, 2)

    origin = _checkout_origin(body.origin_url, request.headers.get("origin"))
    success_url = f"{origin}/credits/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/credits/cancel"

    req = CheckoutSessionRequest(
        amount=_sdk_safe_amount(amount),
        currency="usd",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "source": "da_roastbox",
            "user_id": current_user.id,
            "pack_id": body.pack_id,
            "pack_type": pack["type"],
            "credits": str(pack.get("credits", 0)),
            "days": str(pack.get("days", 0)),
            "name": pack["name"],
        },
    )

    try:
        sc = _checkout()
        resp = await sc.create_checkout_session(req)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Stripe checkout error: %s", e)
        raise HTTPException(status_code=502, detail="Stripe checkout is temporarily unavailable. Please try again.")

    tx = PaymentTransaction(
        user_id=current_user.id,
        stripe_session_id=resp.session_id,
        amount_usd=amount,
        credits=pack.get("credits", 0),
        pack_id=body.pack_id,
        pack_type=pack["type"],
        payment_status="pending",
    )
    await payments_collection.insert_one(tx.model_dump())

    return {"checkout_url": resp.url, "session_id": resp.session_id}


def _extend_plan(user_doc: dict, days: int) -> str:
    existing = user_doc.get("plan_until")
    try:
        base = datetime.fromisoformat(existing) if existing else datetime.now(timezone.utc)
        if base < datetime.now(timezone.utc):
            base = datetime.now(timezone.utc)
    except Exception:
        base = datetime.now(timezone.utc)
    return (base + timedelta(days=days)).isoformat()


def _purchase_update(txn: dict, user_doc: dict):
    """Compute server-authoritative entitlement changes for a tracked checkout."""
    pack_id = txn["pack_id"]
    pack = PRODUCT_CATALOG.get(pack_id) or {}
    ptype = txn.get("pack_type") or pack.get("type") or "credits"
    update_op: dict = {}
    credit_amount = 0
    tx_type = "purchase"
    description = f"Purchase: {pack_id}"

    if ptype == "credits":
        credit_amount = int(txn.get("credits") or pack.get("credits") or 0)
        update_op = {"$inc": {"credits": credit_amount}}
        tx_type = "purchase"

    elif ptype == "premium_personas":
        update_op = {"$set": {"premium_personas_unlocked": True}}
        tx_type = "unlock"
        description = "Unlocked Premium Personas Bundle"

    elif ptype == "premium_voices":
        update_op = {"$set": {"premium_voices_unlocked": True}}
        tx_type = "unlock"
        description = "Unlocked Premium Voices Bundle"

    elif ptype == "roast_battle":
        update_op = {"$set": {"roast_battle_unlocked": True}}
        tx_type = "unlock"
        description = "Unlocked Roast Battle Mode"

    elif ptype == "nsfw_edgier":
        update_op = {"$set": {"nsfw_edgier_unlocked": True}}
        tx_type = "unlock"
        description = "Unlocked Brutality+ Mode"

    elif ptype == "lifetime_founder":
        credit_amount = int(pack.get("credits") or 0)
        update_op = {
            "$set": {
                "lifetime_founder": True,
                "premium_personas_unlocked": True,
                "premium_voices_unlocked": True,
                "roast_battle_unlocked": True,
                "nsfw_edgier_unlocked": True,
            },
            "$inc": {"credits": credit_amount},
        }
        tx_type = "unlock"
        description = "Unlocked Lifetime Founder Pack (+1500 credits, all add-ons forever)"

    elif ptype == "plus_subscription":
        # Pass benefits are computed from the active tier; never turn their
        # temporary privileges into the permanent add-on flags.
        new_until = _extend_plan(user_doc, int(pack.get("days") or 30))
        credit_amount = int(pack.get("credits") or 150)
        # Preserve an active VIP plan, but never revive an expired VIP tier.
        target_tier = "vip" if active_plan_tier(user_doc.get("plan_tier"), user_doc.get("plan_until")) == "vip" else "plus"
        update_op = {
            "$set": {
                "plan_tier": target_tier,
                "plan_until": new_until,
                "plan_renew_on": datetime.now(timezone.utc).strftime("%Y-%m"),
            },
            "$inc": {"credits": credit_amount},
        }
        tx_type = "subscription"
        description = f"RoastBox Plus 30-day pass (+{credit_amount} credits)"

    elif ptype == "vip_subscription":
        new_until = _extend_plan(user_doc, int(pack.get("days") or 30))
        credit_amount = int(pack.get("credits") or 500)
        update_op = {
            "$set": {
                "plan_tier": "vip",
                "plan_until": new_until,
                "plan_renew_on": datetime.now(timezone.utc).strftime("%Y-%m"),
            },
            "$inc": {"credits": credit_amount},
        }
        tx_type = "subscription"
        description = f"RoastBox VIP 30-day pass (+{credit_amount} credits)"

    if not update_op:
        raise RuntimeError(f"Unknown checkout product type: {ptype}")
    return ptype, update_op, credit_amount, tx_type, description


async def _apply_paid_purchase(user_id: str, session_id: str):
    """Fulfill once, with recovery if a process stops between MongoDB writes.

    The entitlement and checkout marker are a single atomic user-document update.
    The deterministic ledger record and final paid status can then be retried; a
    restart cannot double-credit or silently lose a claimed purchase. Existing
    already-paid transactions are left untouched for backwards compatibility.
    """
    tracked = await payments_collection.find_one({"stripe_session_id": session_id, "user_id": user_id})
    if not tracked:
        raise RuntimeError("Paid checkout transaction is not tracked")
    if tracked.get("payment_status") == "paid":
        return
    txn = tracked  # never apply metadata supplied by the caller or a webhook

    for _ in range(12):
        user_doc = await users_collection.find_one({"id": user_id})
        if not user_doc:
            raise RuntimeError("Checkout account no longer exists")
        ptype, update_op, credit_amount, tx_type, description = _purchase_update(txn, user_doc)
        if session_id in user_doc.get("applied_checkout_sessions", []):
            break  # A previous attempt applied the entitlement before failing.
        update_op["$addToSet"] = {"applied_checkout_sessions": session_id}
        condition = {"id": user_id, "applied_checkout_sessions": {"$ne": session_id}}
        if ptype in ("plus_subscription", "vip_subscription"):
            # Different concurrent pass purchases must each extend the latest plan.
            condition.update({"plan_tier": user_doc.get("plan_tier"), "plan_until": user_doc.get("plan_until")})
        result = await users_collection.update_one(condition, update_op)
        if result.modified_count:
            break
    else:
        raise RuntimeError("Could not apply checkout after concurrent account updates; retry")

    ledger_id = f"stripe-checkout:{session_id}"
    ledger = CreditTransaction(
        user_id=user_id, amount=credit_amount, type=tx_type,
        stripe_session_id=session_id, description=description,
    ).model_dump()
    ledger["_id"] = ledger_id
    try:
        await credits_collection.insert_one(ledger)
    except DuplicateKeyError:
        # The other worker already recorded this exact checkout.
        existing = await credits_collection.find_one({"_id": ledger_id, "stripe_session_id": session_id})
        if not existing:
            raise
    await payments_collection.update_one(
        {"stripe_session_id": session_id, "user_id": user_id, "payment_status": {"$ne": "paid"}},
        {"$set": {"payment_status": "paid", "updated_at": datetime.now(timezone.utc).isoformat()}},
    )


@router.get("/status/{session_id}")
async def payment_status(session_id: str, current_user: User = Depends(get_current_user)):
    txn = await payments_collection.find_one({"stripe_session_id": session_id})
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not tracked")
    if txn["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Not your transaction")

    try:
        sc = _checkout()
        status = await sc.get_checkout_status(session_id)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Stripe status error: %s", e)
        raise HTTPException(status_code=502, detail="Could not check Stripe payment status. Please try again.")

    payment_status_str = (status.payment_status or "unknown").lower()

    if payment_status_str == "paid" and txn["payment_status"] != "paid":
        await _apply_paid_purchase(current_user.id, session_id)

    updated_user = await users_collection.find_one({"id": current_user.id}) or {}
    return {
        "payment_status": payment_status_str,
        "pack_type": txn.get("pack_type") or "credits",
        "pack_name": PRODUCT_CATALOG.get(txn["pack_id"], {}).get("name", txn["pack_id"]),
        "amount_total": status.amount_total,
        "currency": status.currency,
        "credits_added": txn.get("credits", 0) if payment_status_str == "paid" else 0,
        "credits_balance": updated_user.get("credits", 0),
        "premium_personas_unlocked": updated_user.get("premium_personas_unlocked", False),
        "premium_voices_unlocked": updated_user.get("premium_voices_unlocked", False),
        "roast_battle_unlocked": updated_user.get("roast_battle_unlocked", False),
        "nsfw_edgier_unlocked": updated_user.get("nsfw_edgier_unlocked", False),
        "lifetime_founder": updated_user.get("lifetime_founder", False),
        "plan_tier": updated_user.get("plan_tier", "free"),
        "plan_until": updated_user.get("plan_until"),
    }


@router.post("/webhook")
async def stripe_webhook(request: Request):
    # The upstream SDK otherwise parses unsigned payloads, letting anyone forge a paid event.
    if not secret_cached("STRIPE_WEBHOOK_SECRET"):
        raise HTTPException(status_code=503, detail="Stripe webhook signing secret is not configured.")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    sc = _checkout()
    try:
        evt = await sc.handle_webhook(payload, sig)
    except Exception as e:
        log.warning("Webhook signature validation failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature")

    if getattr(evt, "payment_status", "").lower() == "paid":
        sid = getattr(evt, "session_id", None)
        if sid:
            txn = await payments_collection.find_one({"stripe_session_id": sid})
            if not txn and (getattr(evt, "metadata", None) or {}).get("source") == "da_roastbox":
                # A provider event can race the initial transaction insert; let
                # Stripe retry rather than acknowledging an untracked purchase.
                raise HTTPException(status_code=503, detail="Checkout is not yet tracked; retry webhook")
            if txn and txn.get("payment_status") != "paid":
                await _apply_paid_purchase(txn["user_id"], sid)
    return {"received": True}
