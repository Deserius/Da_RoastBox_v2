"""Pydantic models for Da RoastBox."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


NEW_ACCOUNT_CREDITS = 25


class User(BaseModel):
    id: str = Field(default_factory=_uid)
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    credits: int = 5  # Legacy fallback only; creation routes explicitly grant NEW_ACCOUNT_CREDITS.
    is_preview: bool = False  # isolated demo account; never a real customer entitlement
    favorite_persona_ids: List[str] = Field(default_factory=list)
    # Add-on entitlements (one-time unlocks, persistent)
    premium_personas_unlocked: bool = False
    premium_voices_unlocked: bool = False
    roast_battle_unlocked: bool = False
    nsfw_edgier_unlocked: bool = False
    lifetime_founder: bool = False  # all add-ons + best perks for life
    # Subscription tier
    plan_tier: str = "free"               # "free" | "plus" | "vip"
    plan_until: Optional[str] = None      # ISO timestamp; null if free
    plan_renew_on: Optional[str] = None   # date string YYYY-MM (last month we granted monthly credits)
    # Free-tier daily roast tracking
    last_free_roast_date: Optional[str] = None   # YYYY-MM-DD
    # BYOK
    has_byok_openai: bool = False
    has_byok_elevenlabs: bool = False
    openai_key_encrypted: Optional[str] = None
    elevenlabs_key_encrypted: Optional[str] = None
    created_at: str = Field(default_factory=_now)


class Session(BaseModel):
    session_token: str
    user_id: str
    expires_at: str


class CreditTransaction(BaseModel):
    id: str = Field(default_factory=_uid)
    user_id: str
    amount: int
    type: str  # "purchase" | "spend" | "refund" | "bonus" | "unlock" | "subscription" | "monthly_grant" | "free_roast"
    stripe_session_id: Optional[str] = None
    description: Optional[str] = None
    created_at: str = Field(default_factory=_now)


class PaymentTransaction(BaseModel):
    id: str = Field(default_factory=_uid)
    user_id: str
    stripe_session_id: str
    amount_usd: float
    credits: int = 0
    pack_id: str
    pack_type: str = "credits"
    # "credits" | "premium_personas" | "premium_voices" | "roast_battle" | "nsfw_edgier"
    # | "lifetime_founder" | "plus_subscription" | "vip_subscription"
    payment_status: str = "pending"
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class RoastRecord(BaseModel):
    id: str = Field(default_factory=_uid)
    user_id: str
    mode: str = "roast"                    # "roast" | "battle"
    battle_style: str = "classic"           # "classic" | "rap"
    heat: str = "hot"                      # mild | hot | fire | inferno
    adult_language: bool = True
    adult_subjects_confirmed: bool = False
    content_rating: str = "21+"
    battle: Optional[Dict[str, Any]] = None  # {"scores": {pid: int}, "winner": pid}
    persona_ids: List[str]
    subject_name: Optional[str] = None
    user_context: Optional[str] = None
    off_limits: Optional[str] = None
    comedy_styles: List[str] = Field(default_factory=list)
    image_count: int = 0
    duration_minutes: int = 3
    roast_tier: str = "standard"           # "standard" | "premium"
    used_premium_voice: bool = False
    used_premium_persona: bool = False
    hd_export: bool = False
    credits_spent: int = 0
    was_free_roast: bool = False
    transcript: List[Dict[str, Any]] = []
    generation_meta: Optional[Dict[str, Any]] = None
    audio_provider: Optional[str] = None
    created_at: str = Field(default_factory=_now)
