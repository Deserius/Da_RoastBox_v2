"""
Da RoastBox — Monetization v5 backend tests.

Covers the new tiered model (free + credit packs + Plus/VIP subs + add-ons + lifetime founder).

NOTE: POST /api/roast/generate is invoked AT MOST ONCE (the free-roast happy path),
per main-agent instruction to conserve LLM credits.
"""
import io
import os
import uuid
import time
import pytest
import requests
from PIL import Image, ImageDraw

from tests._env import BASE_URL
API = f"{BASE_URL}/api"


# ----------------------------- fixtures -----------------------------
@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    return s


@pytest.fixture(scope="module")
def fresh_user(client):
    """Create a brand new user with credits=5 and no entitlements."""
    email = f"TEST_v5_{uuid.uuid4().hex[:10]}@example.com"
    r = client.post(f"{API}/auth/dev-login", json={"email": email, "name": "V5 Tester"}, timeout=15)
    assert r.status_code == 200, f"dev-login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data["session_token"]
    user_id = data["user"]["id"]
    return {"email": email, "token": token, "user_id": user_id,
            "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture(scope="module")
def test_image_bytes():
    """A small 256x256 JPEG with simple shapes."""
    img = Image.new("RGB", (256, 256), color=(180, 60, 60))
    d = ImageDraw.Draw(img)
    d.ellipse([60, 60, 196, 196], fill=(255, 220, 80))
    d.rectangle([100, 100, 156, 156], fill=(30, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ----------------------------- payments / catalog -----------------------------
class TestCatalog:
    def test_packs_returns_11_products_plus_roast_costs(self, client):
        r = client.get(f"{API}/payments/packs", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "packs" in body and "roast_costs" in body
        ids = {p["id"] for p in body["packs"]}
        expected = {
            "credits_starter", "credits_savage", "credits_kingpin", "credits_legend",
            "plus_subscription", "vip_subscription",
            "premium_personas_bundle", "premium_voices_bundle",
            "roast_battle_mode", "nsfw_edgier_mode", "lifetime_founder",
        }
        assert expected.issubset(ids), f"missing pack ids: {expected - ids}"
        assert len(body["packs"]) == 11, f"expected 11 products, got {len(body['packs'])}"

        rc = body["roast_costs"]
        assert rc["standard_roast"] == 5
        assert rc["premium_roast"] == 10
        assert rc["premium_voice"] == 3
        assert rc["premium_persona"] == 5
        assert rc["hd_export"] == 5


# ----------------------------- auth / new fields -----------------------------
class TestAuthFields:
    def test_dev_login_creates_user_with_defaults(self, client):
        email = f"TEST_default_{uuid.uuid4().hex[:8]}@example.com"
        r = client.post(f"{API}/auth/dev-login", json={"email": email}, timeout=15)
        assert r.status_code == 200, r.text
        token = r.json()["session_token"]

        me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        assert me.status_code == 200, me.text
        m = me.json()
        # Default credits & tier
        assert m["credits"] == 5
        assert m["plan_tier"] == "free"
        assert m["last_free_roast_date"] in (None, "")
        # Unlock flags all False
        for f in ("premium_personas_unlocked", "premium_voices_unlocked",
                  "roast_battle_unlocked", "nsfw_edgier_unlocked", "lifetime_founder"):
            assert m[f] is False, f"{f} should be False, got {m[f]}"
        # plan_until is None for free users
        assert m.get("plan_until") in (None, "")

    def test_me_exposes_all_new_fields(self, fresh_user, client):
        r = client.get(f"{API}/auth/me", headers=fresh_user["headers"], timeout=15)
        assert r.status_code == 200, r.text
        m = r.json()
        for field in (
            "roast_battle_unlocked", "nsfw_edgier_unlocked", "lifetime_founder",
            "plan_tier", "plan_until", "last_free_roast_date",
        ):
            assert field in m, f"/auth/me missing new field: {field}"


# ----------------------------- cost-quote -----------------------------
class TestCostQuote:
    def test_standard_quote_free_available_for_new_user(self, fresh_user, client):
        r = client.get(
            f"{API}/roast/cost-quote",
            params={"roast_tier": "standard"},
            headers=fresh_user["headers"], timeout=15,
        )
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["credit_cost"] == 5, f"expected 5, got {q['credit_cost']}"
        assert q["free_available"] is True, "brand-new user should have free roast available"
        assert q["plan_tier"] == "free"
        assert q["credits_balance"] == 5

    def test_premium_all_addons_costs_23_no_free(self, fresh_user, client):
        r = client.get(
            f"{API}/roast/cost-quote",
            params={"roast_tier": "premium", "premium_voice": "true",
                    "premium_persona": "true", "hd_export": "true"},
            headers=fresh_user["headers"], timeout=15,
        )
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["credit_cost"] == 23, f"expected 23 (10+3+5+5), got {q['credit_cost']}"
        assert q["free_available"] is False


# ----------------------------- checkout (Stripe) -----------------------------
CHECKOUT_PACKS = [
    "credits_legend",
    "plus_subscription",
    "vip_subscription",
    "premium_personas_bundle",
    "premium_voices_bundle",
    "roast_battle_mode",
    "nsfw_edgier_mode",
    "lifetime_founder",
]


class TestCheckout:
    @pytest.mark.parametrize("pack_id", CHECKOUT_PACKS)
    def test_checkout_returns_stripe_url(self, fresh_user, client, pack_id):
        r = client.post(
            f"{API}/payments/checkout",
            json={"pack_id": pack_id, "origin_url": BASE_URL},
            headers=fresh_user["headers"], timeout=30,
        )
        assert r.status_code == 200, f"{pack_id}: {r.status_code} {r.text}"
        body = r.json()
        assert "checkout_url" in body and body["checkout_url"], f"{pack_id}: no checkout_url"
        assert body["checkout_url"].startswith("http"), f"{pack_id}: bad url {body['checkout_url']}"
        assert "session_id" in body and body["session_id"]
        # Confirm Stripe-flavored URL
        assert "stripe" in body["checkout_url"].lower() or "checkout" in body["checkout_url"].lower()

    def test_checkout_invalid_pack_returns_400(self, fresh_user, client):
        r = client.post(
            f"{API}/payments/checkout",
            json={"pack_id": "invalid_pack", "origin_url": BASE_URL},
            headers=fresh_user["headers"], timeout=15,
        )
        assert r.status_code == 400, f"got {r.status_code}: {r.text}"


# ----------------------------- premium gating (402) -----------------------------
class TestPremiumGating:
    def test_premium_persona_locked_returns_402(self, fresh_user, client, test_image_bytes):
        files = [("images", ("a.jpg", test_image_bytes, "image/jpeg"))]
        data = {
            "persona_ids": "persona_p1",
            "duration_minutes": "3",
            "roast_tier": "standard",
            "use_premium_voice": "false",
            "hd_export": "false",
        }
        r = client.post(
            f"{API}/roast/generate",
            data=data, files=files,
            headers=fresh_user["headers"], timeout=30,
        )
        assert r.status_code == 402, f"expected 402, got {r.status_code}: {r.text}"
        detail = (r.json().get("detail") or "").lower()
        assert ("premium personas bundle" in detail) or ("vip" in detail), \
            f"detail should mention Premium Personas Bundle or VIP, got: {detail}"

    def test_premium_voice_locked_returns_402(self, fresh_user, client, test_image_bytes):
        files = [("images", ("a.jpg", test_image_bytes, "image/jpeg"))]
        data = {
            "persona_ids": "persona_1",
            "duration_minutes": "3",
            "roast_tier": "standard",
            "use_premium_voice": "true",
            "hd_export": "false",
        }
        r = client.post(
            f"{API}/roast/generate",
            data=data, files=files,
            headers=fresh_user["headers"], timeout=30,
        )
        assert r.status_code == 402, f"expected 402, got {r.status_code}: {r.text}"
        detail = (r.json().get("detail") or "").lower()
        # mentions Voice Bundle or Plus/VIP
        assert "voice" in detail and ("bundle" in detail or "plus" in detail or "vip" in detail), \
            f"detail should mention Voice Bundle or Plus/VIP, got: {detail}"


# ----------------------------- free roast happy path (single LLM call) -----------------------------
class TestFreeRoast:
    """Exactly ONE call to POST /api/roast/generate per main-agent budget."""

    def test_brand_new_user_free_roast_then_quote_unavailable(
        self, fresh_user, client, test_image_bytes
    ):
        # Sanity: free should be available before
        q1 = client.get(
            f"{API}/roast/cost-quote",
            params={"roast_tier": "standard"},
            headers=fresh_user["headers"], timeout=15,
        ).json()
        assert q1["free_available"] is True, "precondition: free roast should be available"

        files = [("images", ("a.jpg", test_image_bytes, "image/jpeg"))]
        data = {
            "persona_ids": "persona_1,persona_5",
            "duration_minutes": "3",
            "roast_tier": "standard",
            "use_premium_voice": "false",
            "hd_export": "false",
            "subject_name": "Tester",
            "user_context": "QA smoke test",
        }
        t0 = time.time()
        r = client.post(
            f"{API}/roast/generate",
            data=data, files=files,
            headers=fresh_user["headers"], timeout=70,
        )
        dt = time.time() - t0
        assert r.status_code == 200, f"free roast failed in {dt:.1f}s: {r.status_code} {r.text[:500]}"
        body = r.json()

        assert body["was_free_roast"] is True, f"was_free_roast should be True: {body}"
        assert body["credits_spent"] == 0, f"credits_spent should be 0: {body}"
        assert body["credits_remaining"] == 5, f"credits_remaining should be 5 (unchanged): {body}"
        assert body.get("transcript"), "transcript should not be empty"

        # Verify free no longer available
        q2 = client.get(
            f"{API}/roast/cost-quote",
            params={"roast_tier": "standard"},
            headers=fresh_user["headers"], timeout=15,
        ).json()
        assert q2["free_available"] is False, \
            f"after free roast, free_available must be False: {q2}"
        assert q2["credit_cost"] == 5
        assert q2["credits_balance"] == 5

        # /auth/me reflects last_free_roast_date set to today
        me = client.get(f"{API}/auth/me", headers=fresh_user["headers"], timeout=15).json()
        assert me["last_free_roast_date"], "last_free_roast_date should be set after free roast"
        assert me["credits"] == 5
