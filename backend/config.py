"""Centralised runtime settings. Required vars fail fast; feature flags default to off."""
import os
import math
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")


def _flag(name: str) -> bool:
    return os.environ.get(name, "false").strip().lower() in ("1", "true", "yes")


MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
# Optional direct hosted OpenAI alternative; the original Emergent gateway takes precedence.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
AI_DEFAULT_PROVIDER = os.environ.get("AI_DEFAULT_PROVIDER", "openai").strip().lower()
if AI_DEFAULT_PROVIDER not in ("openai", "emergent"):
    raise ValueError("AI_DEFAULT_PROVIDER must be openai or emergent")
# The default writer is a single multimodal OpenRouter call (photos + jokes).
# OpenAI/Emergent remain separately configured backups and speech providers.
# Never send an OpenAI/BYOK credential to OpenRouter.
ROAST_WRITER_PROVIDER = os.environ.get("ROAST_WRITER_PROVIDER", "openrouter").strip().lower()
if ROAST_WRITER_PROVIDER not in ("existing", "openrouter"):
    raise ValueError("ROAST_WRITER_PROVIDER must be existing or openrouter")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
ROAST_WRITER_MODEL = os.environ.get("ROAST_WRITER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free").strip()
# Multimodal is the requested Claude -> GPT-4.1 -> GPT-4o writer/vision chain.
# The older separate-observation free/creative profiles remain opt-in.
ROAST_WRITER_PROFILE = os.environ.get("ROAST_WRITER_PROFILE", "multimodal").strip().lower()
if ROAST_WRITER_PROFILE not in ("free", "creative", "multimodal"):
    raise ValueError("ROAST_WRITER_PROFILE must be free, creative or multimodal")
ROAST_OPENROUTER_MODELS = tuple(dict.fromkeys(v.strip() for v in os.environ.get(
    "ROAST_OPENROUTER_MODELS", "anthropic/claude-sonnet-4.5,openai/gpt-4.1,openai/gpt-4o").split(",") if v.strip()))
if not ROAST_OPENROUTER_MODELS or len(ROAST_OPENROUTER_MODELS) > 6:
    raise ValueError("Configure one to six OpenRouter writer models")
ROAST_BACKUP_PROVIDERS = tuple(dict.fromkeys(v.strip().lower() for v in os.environ.get(
    "ROAST_BACKUP_PROVIDERS", "openai").split(",") if v.strip()))
if any(v not in ("emergent", "openai") for v in ROAST_BACKUP_PROVIDERS):
    raise ValueError("ROAST_BACKUP_PROVIDERS supports emergent,openai only")
ROAST_PAID_PRIMARY_MODEL = os.environ.get("ROAST_PAID_PRIMARY_MODEL", "thedrummer/cydonia-24b-v4.1").strip()
ROAST_PAID_BACKUP_MODEL = os.environ.get("ROAST_PAID_BACKUP_MODEL", "cognitivecomputations/dolphin-mistral-24b-venice-edition").strip()
# OpenRouter provider price ceilings, dollars per million tokens. These are not
# a daily spending budget; set a key-level budget in OpenRouter separately.
ROAST_MAX_INPUT_USD_PER_M = float(os.environ.get("ROAST_MAX_INPUT_USD_PER_M", "3.00"))
ROAST_MAX_OUTPUT_USD_PER_M = float(os.environ.get("ROAST_MAX_OUTPUT_USD_PER_M", "15.00"))
if not all(math.isfinite(v) and v >= 0 for v in (ROAST_MAX_INPUT_USD_PER_M, ROAST_MAX_OUTPUT_USD_PER_M)):
    raise ValueError("OpenRouter price ceilings must be finite non-negative numbers")
ROAST_FREE_WRITER_ONLY = os.environ.get("ROAST_FREE_WRITER_ONLY", "false").strip().lower() in ("1", "true", "yes")
ROAST_FREE_BACKUP_MODEL = os.environ.get("ROAST_FREE_BACKUP_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free").strip()
# Model choice per show tier. Premium buys the strongest configured creative model;
# standard uses the cheaper mid-tier creative model so quality is not traded away
# entirely for speed. Backups stay unchanged and are tried after a failed primary.
ROAST_PAID_STANDARD_MODEL = os.environ.get("ROAST_PAID_STANDARD_MODEL",
                                           "cognitivecomputations/dolphin-mistral-24b-venice-edition").strip()
ROAST_FREE_PREMIUM_MODEL = os.environ.get("ROAST_FREE_PREMIUM_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free").strip()

ROAST_SPEED_PROFILE = os.environ.get("ROAST_SPEED_PROFILE", "balanced").strip().lower()
if ROAST_SPEED_PROFILE not in ("fast", "balanced", "quality"):
    raise ValueError("ROAST_SPEED_PROFILE must be fast, balanced or quality")


def _speed(name: str, fast, balanced, quality):
    """Preset chosen by ROAST_SPEED_PROFILE; any ROAST_<NAME> env var overrides it."""
    raw = os.environ.get(f"ROAST_{name}")
    if raw not in (None, ""):
        return type(fast)(raw)
    return {"fast": fast, "balanced": balanced, "quality": quality}[ROAST_SPEED_PROFILE]


# Lower timeouts fail faster and fall through to the backup model instead of
# stalling a paid request. Streaming starts voice work while text is still being written.
ROAST_WRITER_DEADLINE_S = float(os.environ.get("ROAST_WRITER_DEADLINE_S", "75"))
if not math.isfinite(ROAST_WRITER_DEADLINE_S) or not 1 <= ROAST_WRITER_DEADLINE_S <= 300:
    raise ValueError("ROAST_WRITER_DEADLINE_S must be between 1 and 300 seconds")
ROAST_WRITER_TIMEOUT_S = _speed("WRITER_TIMEOUT_S", 22, 32, 50)
ROAST_WRITER_RETRY = _speed("WRITER_RETRY", 0, 1, 1) == 1
ROAST_VISION_TIMEOUT_S = _speed("VISION_TIMEOUT_S", 18, 25, 35)
ROAST_VISION_MAX_TOKENS = _speed("VISION_MAX_TOKENS", 600, 900, 1400)
# Measured against the real writer: a fully instrumented beat (text, emotion,
# delivery, laugh, reaction, pauses, image_index) costs roughly 420 output
# tokens, and reasoning models spend part of the budget thinking. Undersized
# budgets cut a finished set off mid-beat, which reads as a failed show.
ROAST_WRITER_MAX_TOKENS = _speed("WRITER_MAX_TOKENS", 6000, 8000, 9000)
ROAST_WRITER_TOKENS_PER_BEAT = _speed("WRITER_TOKENS_PER_BEAT", 440, 480, 560)
# Reasoning models spend part of the budget thinking; keep headroom so long
# shows are not truncated into an unusable script.
ROAST_WRITER_TOKEN_BASE = _speed("WRITER_TOKEN_BASE", 1100, 1300, 1500)
# How much to grow the budget when a writer stops on the token limit.
ROAST_WRITER_TRUNCATION_RETRY = _speed("WRITER_TRUNCATION_RETRY", 1, 1, 1) == 1
ROAST_TTS_CONCURRENCY = _speed("TTS_CONCURRENCY", 32, 24, 16)
ROAST_TTS_TIMEOUT_S = _speed("TTS_TIMEOUT_S", 14, 20, 28)
# Optional OpenRouter reasoning effort ("low" is fastest). Empty means the
# provider default is used and no reasoning parameter is sent.
ROAST_REASONING_EFFORT = os.environ.get("ROAST_REASONING_EFFORT", _speed("REASONING_EFFORT", "low", "", "")).strip().lower()
ROAST_STREAM_TTS = _speed("STREAM_TTS", 1, 1, 1) == 1
ROAST_TTS_CACHE = _speed("TTS_CACHE", 1, 1, 1) == 1
# Optional OpenRouter provider pinning, e.g. "venice/fp8". Comma separated.
ROAST_OPENROUTER_PROVIDER_ONLY = tuple(v.strip() for v in os.environ.get("ROAST_OPENROUTER_PROVIDER_ONLY", "").split(",") if v.strip())
# When a provider is pinned, fail with the upstream error instead of silently rerouting.
ROAST_OPENROUTER_ALLOW_FALLBACKS = os.environ.get("ROAST_OPENROUTER_ALLOW_FALLBACKS", "").strip().lower()
ROAST_POLLINATIONS_FALLBACK = os.environ.get("ROAST_POLLINATIONS_FALLBACK", "false").strip().lower() in ("1", "true", "yes")
ROAST_ALLOW_PAID_WRITER_FALLBACK = os.environ.get("ROAST_ALLOW_PAID_WRITER_FALLBACK", "false").strip().lower() in ("1", "true", "yes")
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
# Optional safety rail for staging: reject live/restricted-live Stripe keys.
STRIPE_TEST_ONLY = os.environ.get("STRIPE_TEST_ONLY", "true").strip().lower() in ("1", "true", "yes")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
# Platform-injected; may be "" so use `or`.
INTEGRATION_PROXY_URL = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
TTS_MODEL = os.environ.get("TTS_MODEL", "gpt-4o-mini-tts")
# Local playback mastering applies to old and new persona clips, without a
# provider call. Bound the target to avoid damaging loudness or extreme gain.
VOICE_LEVELING_ENABLED = os.environ.get("VOICE_LEVELING_ENABLED", "true").strip().lower() in ("1", "true", "yes")
try:
    VOICE_TARGET_RMS_DBFS = max(-27.0, min(-16.0, float(os.environ.get("VOICE_TARGET_RMS_DBFS", "-19"))))
except ValueError:
    VOICE_TARGET_RMS_DBFS = -19.0
JWT_SECRET = os.environ["JWT_SECRET"]
if not JWT_SECRET.strip():
    raise ValueError("JWT_SECRET must be a non-empty, persistent secret")
# Same-origin API requests need no CORS. Never default to credentialed wildcard access.
CORS_ORIGINS = [o.strip().rstrip("/") for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
# Optional public frontend origin; required for predictable checkout returns in production.
# Render supplies its public onrender.com URL automatically. A custom domain
# must explicitly override APP_BASE_URL so checkout return origins are pinned.
APP_BASE_URL = (os.environ.get("APP_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
ALLOW_DEV_LOGIN = _flag("ALLOW_DEV_LOGIN")
ENABLE_PREVIEW_LOGIN = _flag("ENABLE_PREVIEW_LOGIN")
# Off by default: only enable in a disposable, cost-capped workspace preview.
ALLOW_PREVIEW_HOSTED_AI = _flag("ALLOW_PREVIEW_HOSTED_AI")
# Offline demo provider. This workspace cannot complete TLS to any provider, so
# real generations fail with a connection error regardless of key validity.
# Enabling this generates scripts and audio locally so the app can be exercised
# end to end. Refused in production by the runtime guard.
DRY_RUN = _flag("ROASTBOX_DRY_RUN")
# Counted per UTC day across all preview accounts. -1 means unlimited: usage is
# still recorded for visibility, but nothing is blocked. 0 keeps them disabled.
PREVIEW_HOSTED_DAILY_SHOW_LIMIT = int(os.environ.get("PREVIEW_HOSTED_DAILY_SHOW_LIMIT", "5") or 5)
PREVIEW_HOSTED_DAILY_VOICE_LIMIT = int(os.environ.get("PREVIEW_HOSTED_DAILY_VOICE_LIMIT", "10") or 10)
# Preview accounts cannot buy credits, so this removes the credit requirement
# (and the debit) for them. Off by default for any deployment that bills users.
PREVIEW_UNLIMITED_CREDITS = _flag("PREVIEW_UNLIMITED_CREDITS")
# Google sign-in. The original build delegates OAuth to a managed provider URL
# (see routes/auth.py). Supplying a pair of Google OAuth client credentials lets
# an operator point the app at their own consent screen instead.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
# Managed provider endpoints (default). Override to use a self-hosted broker.
GOOGLE_AUTH_URL = (os.environ.get("GOOGLE_AUTH_URL")
                   or "https://demobackend.emergentagent.com/auth/v1/env/oauth").strip()
GOOGLE_SESSION_URL = (os.environ.get("GOOGLE_SESSION_URL")
                      or "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data").strip()

# Owner settings console: lets an operator enter provider credentials from the
# running app instead of hand-editing the environment. Intended for a disposable
# preview only; it always requires a shared passphrase and is never on by default.
ALLOW_RUNTIME_SETTINGS = _flag("ALLOW_RUNTIME_SETTINGS")
# Shared passphrase for the settings console. Empty = console cannot be unlocked.
RUNTIME_SETTINGS_PASSPHRASE = os.environ.get("RUNTIME_SETTINGS_PASSPHRASE", "").strip()
# Optional comma-separated user ids/emails allowed to open the console. Empty =
# any signed-in preview/test account may, once it has the passphrase.
RUNTIME_SETTINGS_ADMINS = tuple(
    value.strip().lower()
    for value in os.environ.get("RUNTIME_SETTINGS_ADMINS", "").split(",")
    if value.strip()
)
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local").strip().lower()
if STORAGE_BACKEND not in ("emergent", "local", "vercel_blob"):
    raise ValueError("STORAGE_BACKEND must be emergent, local or vercel_blob")
# Production can point this at a persistent disk; the default preserves the
# existing local-development layout. Never serve this directory as static files.
LOCAL_STORAGE_DIR = Path(os.environ.get("LOCAL_STORAGE_DIR") or ROOT_DIR / "local_storage").expanduser().resolve()
ALLOW_SOURCE_DOWNLOAD = _flag("ALLOW_SOURCE_DOWNLOAD")

# Optional first-party email sign-in. Disabled unless explicitly enabled; the
# mail transport always uses TLS, and verification links use APP_BASE_URL.
EMAIL_AUTH_ENABLED = _flag("EMAIL_AUTH_ENABLED")
EMAIL_TRANSPORT = os.environ.get("EMAIL_TRANSPORT", "smtp").strip().lower()
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
try:
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
except ValueError:
    SMTP_PORT = 0
SMTP_TLS_MODE = os.environ.get("SMTP_TLS_MODE", "starttls").strip().lower()
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = (os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_FROM") or "").strip()

AUDIO_DIR = Path(os.environ.get("AUDIO_CACHE_DIR") or ROOT_DIR / "audio_cache").expanduser().resolve()
AUDIO_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
DATA_DIR = ROOT_DIR / "data"
APP_VERSION = "7.4.1"
