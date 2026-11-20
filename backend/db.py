"""MongoDB connection and collections."""
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URL, DB_NAME

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

users_collection = db["users"]
sessions_collection = db["sessions"]
roasts_collection = db["roasts"]
credits_collection = db["credit_transactions"]
payments_collection = db["payment_transactions"]
voice_previews_collection = db["voice_previews"]
# Additional punchline samples live separately so the original one-per-persona
# preview cache and its existing unique index remain compatible.
voice_preview_samples_collection = db["voice_preview_samples"]
voice_preview_leases_collection = db["voice_preview_leases"]
reels_collection = db["reels"]
preview_usage_collection = db["preview_hosted_usage"]
email_credentials_collection = db["email_credentials"]
email_tokens_collection = db["email_tokens"]
email_rate_limits_collection = db["email_auth_rate_limits"]


async def ensure_indexes():
    await users_collection.create_index("id", unique=True)
    await users_collection.create_index("email", unique=True)
    await sessions_collection.create_index("session_token", unique=True)
    await email_credentials_collection.create_index("email", unique=True)
    await email_credentials_collection.create_index("user_id", unique=True)
    await email_tokens_collection.create_index("expires_at", expireAfterSeconds=0)
    await email_tokens_collection.create_index([("email", 1), ("purpose", 1)])
    await email_rate_limits_collection.create_index("expires_at", expireAfterSeconds=0)
    await roasts_collection.create_index([("user_id", 1), ("created_at", -1)])
    await roasts_collection.create_index([("billing_version", 1), ("billing_state", 1), ("billing_staged_at", 1)])
    await roasts_collection.create_index([("user_id", 1), ("transcript.audio_url", 1)])
    await payments_collection.create_index("stripe_session_id", unique=True)
    await payments_collection.create_index([("user_id", 1), ("created_at", -1)])
    await credits_collection.create_index("user_id")
    await credits_collection.create_index([("user_id", 1), ("created_at", -1)])
    await roasts_collection.create_index("share_id", unique=True, sparse=True)
    await voice_previews_collection.create_index("persona_id", unique=True)
    await voice_preview_samples_collection.create_index([("persona_id", 1), ("sample", 1)], unique=True)
    await voice_preview_samples_collection.create_index("filename")
    await voice_preview_leases_collection.create_index("expires_at", expireAfterSeconds=0)
    await reels_collection.create_index("id", unique=True)
    await reels_collection.create_index("roast_id")
    await reels_collection.create_index([("status", 1), ("refund_pending", 1)])
