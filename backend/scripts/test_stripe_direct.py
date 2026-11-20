#!/usr/bin/env python3
"""Offline checks that checkout/webhooks work without the Emergent SDK.

Proves the replacement layer: no emergentintegrations import, correct Stripe
sessions, signature rejection, and event normalisation.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        FAILS.append(name)
        print(f"  FAIL  {name} {detail}")


def main() -> int:
    # 1. The old vendor module must be gone from the import graph.
    offenders = []
    for py in Path(".").rglob("*.py"):
        if "scripts" in py.parts or "tests" in py.parts:
            continue
        text = py.read_text(encoding="utf-8", errors="replace")
        if "import emergentintegrations" in text or "from emergentintegrations" in text:
            offenders.append(str(py))
    check("no source file imports emergentintegrations", not offenders, f"-> {offenders}")

    import routes.payments  # noqa: F401  - this import used to fail outright
    check("routes.payments imports", True)

    from services.stripe_checkout import StripeCheckout, CheckoutSessionRequest

    check("no vendor import in payments.py",
          "emergentintegrations" not in Path("routes/payments.py").read_text())

    sc = StripeCheckout(api_key="sk_test_fake", webhook_secret="whsec_fake")

    # 2. Amount guard happens before any network call.
    try:
        asyncio.run(sc.create_checkout_session(CheckoutSessionRequest(
            amount=0.10, success_url="http://localhost:3000/ok",
            cancel_url="http://localhost:3000/no")))
        check("below-minimum amount rejected", False)
    except ValueError:
        check("below-minimum amount rejected", True)

    # 3. Missing signature is refused.
    try:
        asyncio.run(sc.handle_webhook(b"{}", ""))
        check("missing signature rejected", False)
    except ValueError:
        check("missing signature rejected", True)

    # 4. Forged signature is refused by Stripe's verifier.
    try:
        asyncio.run(sc.handle_webhook(b'{"id":"evt_1"}', "t=1,v1=deadbeef"))
        check("forged signature rejected", False)
    except Exception as exc:
        check("forged signature rejected", type(exc).__name__ == "SignatureVerificationError")

    # 5. A valid-looking session event normalises to paid + amount in dollars.
    ev = StripeCheckout._normalise({
        "id": "evt_9", "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_1", "payment_status": "paid", "amount_total": 500,
                            "metadata": {"source": "da_roastbox", "credits": "100"}}}})
    check("session event -> paid", ev.payment_status == "paid")
    check("session event -> session id", ev.session_id == "cs_1")
    check("session event -> dollars", ev.amount_usd == 5.0)
    check("session event -> metadata", ev.metadata.get("source") == "da_roastbox")

    # 6. payment_intent.succeeded also counts as paid.
    ev2 = StripeCheckout._normalise({
        "id": "pi_1", "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_1", "amount_total": 250, "metadata": {}}}})
    check("payment_intent -> paid", ev2.payment_status == "paid")

    # 7. No Emergent key needed anywhere for the stock install.
    import config
    check("defaults are local-first",
          config.AI_DEFAULT_PROVIDER == "openai" and config.STORAGE_BACKEND == "local")

    print()
    if FAILS:
        print(f"FAILED: {len(FAILS)} check(s): {', '.join(FAILS)}")
        return 1
    print("PASS: Stripe runs directly, no Emergent SDK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
