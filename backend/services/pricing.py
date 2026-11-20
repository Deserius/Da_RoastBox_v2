"""Product catalog + per-roast credit cost engine (server-authoritative pricing)."""

PRODUCT_CATALOG = {
    # ---- Credit Packs (never expire) ----
    "credits_starter": {"type": "credits", "credits": 50, "amount_usd": 4.99,
                        "name": "Starter Pack", "tagline": "50 credits — never expire"},
    "credits_savage": {"type": "credits", "credits": 125, "amount_usd": 9.99,
                       "name": "Savage Pack", "tagline": "125 credits — most popular", "highlight": True},
    "credits_kingpin": {"type": "credits", "credits": 300, "amount_usd": 19.99,
                        "name": "Kingpin Pack", "tagline": "300 credits — best value"},
    "credits_legend": {"type": "credits", "credits": 1000, "amount_usd": 49.99,
                       "name": "Legend Pack", "tagline": "1000 credits — heavyweight champion"},

    # The exported checkout makes a one-time charge, not a recurring subscription.
    "plus_subscription": {
        "type": "plus_subscription", "credits": 150, "days": 30, "amount_usd": 14.99,
        "name": "RoastBox Plus",
        "tagline": "150 credits · Premium Voices · 30-day pass",
        "highlight": True,
        "perks": ["150 credits granted with purchase", "Premium voices unlocked", "30 days of Plus access", "No automatic renewal"],
    },
    "vip_subscription": {
        "type": "vip_subscription", "credits": 500, "days": 30, "amount_usd": 29.99,
        "name": "RoastBox VIP",
        "tagline": "500 credits · all 15 premium personas & voices · 30-day pass",
        "perks": ["500 credits granted with purchase", "All 15 Premium Personas unlocked", "All Premium Voices unlocked",
                  "10% off credit packs while VIP is active", "No automatic renewal"],
    },

    # ---- One-time Add-ons ----
    "premium_personas_bundle": {
        "type": "premium_personas", "credits": 0, "amount_usd": 9.99,
        "name": "Premium Personas Bundle",
        "tagline": "Unlock all 15 elite roasters forever — Big Tony, Duchess Venom, Sgt. Savage, Queen Clapback & more",
    },
    "premium_voices_bundle": {
        "type": "premium_voices", "credits": 0, "amount_usd": 9.99,
        "name": "Premium Voices Bundle",
        "tagline": "HD studio-grade ElevenLabs voices on every persona, forever",
    },
    "roast_battle_mode": {
        "type": "roast_battle", "credits": 0, "amount_usd": 4.99,
        "name": "Roast Battle Mode",
        "tagline": "Head-to-head 1v1 roast duels with crowd-judged winner",
    },
    "nsfw_edgier_mode": {
        "type": "nsfw_edgier", "credits": 0, "amount_usd": 9.99,
        "name": "Brutality+ Mode",
        "tagline": "Extra filthy, extra dark, extra brutal — for grown-up audiences only",
    },
    "lifetime_founder": {
        "type": "lifetime_founder", "credits": 1500, "amount_usd": 99.99,
        "name": "Lifetime Founder Pack",
        "tagline": "ALL add-ons + 1500 bonus credits + Founder badge — one-time, forever",
        "highlight": True,
        "perks": ["All Premium Personas FOREVER", "All Premium Voices FOREVER",
                  "Roast Battle + Brutality+ Modes", "1500 bonus credits"],
    },
}

ROAST_COSTS = {
    "standard_roast": 5,
    "premium_roast": 10,
    "premium_voice": 3,
    "premium_persona": 5,  # charged once even if multiple premium personas picked
    "hd_export": 5,
}

VIP_CREDIT_DISCOUNT = 0.90


def compute_roast_cost(*, roast_tier: str, uses_premium_voice: bool,
                       uses_premium_persona: bool, hd_export: bool) -> int:
    cost = ROAST_COSTS["premium_roast"] if roast_tier == "premium" else ROAST_COSTS["standard_roast"]
    if uses_premium_voice:
        cost += ROAST_COSTS["premium_voice"]
    if uses_premium_persona:
        cost += ROAST_COSTS["premium_persona"]
    if hd_export:
        cost += ROAST_COSTS["hd_export"]
    return cost
