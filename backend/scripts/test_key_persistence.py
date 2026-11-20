"""Offline checks for credential validation and .env persistence.

Uses a throwaway .env target so the real backend/.env is never touched, and
makes no provider calls that depend on network reachability.
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "roastbox_keys_test")
os.environ.setdefault("JWT_SECRET", "0123456789abcdef0123456789abcdef")
os.environ["APP_ENV"] = "development"

from services import env_writer, key_validator  # noqa: E402


def check(name, condition, detail=""):
    if not condition:
        raise AssertionError(f"{name} failed{': ' + detail if detail else ''}")
    print(f"PASS: {name}")


def test_writer_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / ".env"
        env_writer.SECRETS_FILE = target

        written = env_writer.write_values({"OPENAI_API_KEY": "sk-abc", "ELEVENLABS_API_KEY": ""})
        text = target.read_text()
        check("writer creates the file", target.exists())
        check("writer records the key", 'OPENAI_API_KEY="sk-abc"' in text, text)
        check("writer reports what it wrote", "OPENAI_API_KEY" in written)

        # A second write must replace in place, not duplicate the key.
        env_writer.write_values({"OPENAI_API_KEY": "sk-xyz"})
        text = target.read_text()
        check("rewrite replaces instead of appending", text.count("OPENAI_API_KEY") == 1, text)
        check("rewrite keeps the newest value", 'OPENAI_API_KEY="sk-xyz"' in text)

        # Comments and unrelated lines survive.
        target.write_text("# keep me\nOTHER_KEY=1\n")
        env_writer.write_values({"OPENAI_API_KEY": "sk-1"})
        text = target.read_text()
        check("existing comments are preserved", "# keep me" in text, text)
        check("unrelated keys are preserved", "OTHER_KEY=1" in text, text)

        # Values with spaces, '#' and '$' must round-trip through dotenv.
        env_writer.write_values({"GOOGLE_CLIENT_SECRET": "GOCSPX-a b#c$d"})
        text = target.read_text()
        check("special characters are quoted", '"GOCSPX-a b#c$d"' in text, text)
        try:
            from dotenv import dotenv_values
            parsed = dotenv_values(str(target))
            check("dotenv parses the hosted value back", parsed.get("GOOGLE_CLIENT_SECRET") == "GOCSPX-a b#c$d", str(parsed))
        except ImportError:
            print("SKIP: python-dotenv unavailable for parse check")

        check("key listing never returns values", "sk-1" not in str(env_writer.read_keys()))

        # A newline must be refused rather than producing a broken file.
        try:
            env_writer.write_values({"OPENAI_API_KEY": "sk-1\nINJECTED=1"})
            raise AssertionError("newline injection was not refused")
        except env_writer.EnvWriteError:
            print("PASS: newline injection is refused")

        # A key name that is not a bare identifier must be refused.
        try:
            env_writer.write_values({"bad key!": "x"})
            raise AssertionError("invalid key name was not refused")
        except env_writer.EnvWriteError:
            print("PASS: invalid key names are refused")


def test_validation_shapes():
    async def run():
        bad = await key_validator.validate("OPENAI_API_KEY", "nope")
        check("OpenAI shape rejected without a network call", bad["status"] == key_validator.INVALID, bad["detail"])

        bad2 = await key_validator.validate("STRIPE_API_KEY", "pk_public_key")
        check("Stripe public key rejected", bad2["status"] == key_validator.INVALID, bad2["detail"])

        bad3 = await key_validator.validate("GOOGLE_CLIENT_ID", "12345")
        check("Google client id shape rejected", bad3["status"] == key_validator.INVALID)

        good = await key_validator.validate("GOOGLE_CLIENT_ID", "1-abc.apps.googleusercontent.com")
        check("valid Google client id accepted", good["status"] == "shape-ok", good["detail"])

        secret = await key_validator.validate("GOOGLE_CLIENT_SECRET", "GOCSPX-abcdef")
        check("valid Google client secret accepted", secret["status"] == "shape-ok")

        hook = await key_validator.validate("STRIPE_WEBHOOK_SECRET", "whsec_1234567890abcdef")
        check("valid webhook secret accepted", hook["status"] == "shape-ok")

        model = await key_validator.validate("ROAST_WRITER_MODEL", "vendor/model:free")
        check("valid model id accepted", model["status"] == "shape-ok")

        spaced = await key_validator.validate("ROAST_WRITER_MODEL", "has spaces")
        check("model id with spaces rejected", spaced["status"] == key_validator.INVALID)

        empty = await key_validator.validate("OPENAI_API_KEY", "   ")
        check("empty value rejected", empty["status"] == key_validator.INVALID)

        # An unreachable provider must not be treated as a rejection.
        unreachable = await key_validator.validate("OPENROUTER_API_KEY", "sk-or-v1-abcdefghijklmnop")
        check("offline provider yields 'unchecked', not 'invalid'",
              unreachable["status"] in (key_validator.UNCHECKED, key_validator.VALID), unreachable)

        check("only a rejection blocks a save",
              key_validator.blocking_status(key_validator.INVALID)
              and not key_validator.blocking_status(key_validator.UNCHECKED))

    asyncio.run(run())


def test_gitignore_protection():
    # The real project .gitignore must cover backend/.env; the file is written
    # only when it is missing a rule, so this asserts the protected end state.
    check("backend/.env is gitignored in this project", env_writer.is_gitignored())

    with tempfile.TemporaryDirectory() as tmp:
        gi = Path(tmp) / ".gitignore"
        gi.write_text("node_modules/\n")
        original_project, original_gi = env_writer.PROJECT_ROOT, env_writer.PROJECT_ROOT
        env_writer.PROJECT_ROOT = Path(tmp)
        try:
            added = env_writer.ensure_gitignored()
            text = gi.read_text()
            check("ensure_gitignored adds the rule", added and "backend/.env" in text, text)
            check("ensure_gitignored preserves prior content", "node_modules/" in text, text)
            check("idempotent on a second call", env_writer.ensure_gitignored() is False)
        finally:
            env_writer.PROJECT_ROOT = original_project


test_writer_roundtrip()
test_validation_shapes()
test_gitignore_protection()
print("PASS: credential validation warnings and .env persistence are safe")
