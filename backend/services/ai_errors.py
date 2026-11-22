"""Shared AI-provider error classification.

OpenAI (and OpenRouter, which proxies the same error shapes) reuses HTTP 429
for two very different situations: a transient burst rate limit (worth
retrying in seconds) and an account with no billing credits/quota (a terminal
condition until the operator adds money - retrying it is a guaranteed-to-fail
network round trip, and telling the user to "try again in a minute" is
actively misleading). This module gives every call site one accurate way to
tell them apart.
"""
QUOTA_MARKERS = ("insufficient_quota", "credit_balance_exhausted", "billing_not_active",
                 "exceeded your current quota", "insufficient credits")


def is_quota_exhausted_error(exc: BaseException) -> bool:
    """True for "this account has no billing credits/quota", not a generic rate limit."""
    text = str(exc).lower()
    return any(marker in text for marker in QUOTA_MARKERS)
