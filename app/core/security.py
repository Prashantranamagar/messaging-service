import hashlib
import hmac
import time

import redis.asyncio as aioredis
from fastapi import Depends, Header, Request
from fastapi.security import APIKeyHeader

from app.core.config import settings
from app.core.exceptions import RateLimitError, UnauthorizedError

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(str(settings.REDIS_URL), decode_responses=True)
    return _redis


api_key_scheme = APIKeyHeader(name=settings.API_KEY_HEADER, auto_error=False)


class ClientIdentity:
    def __init__(self, client_id: str):
        self.client_id = client_id


async def get_current_client(api_key: str | None = Depends(api_key_scheme)) -> ClientIdentity:
    """Validates the API key supplied via the configured header."""
    if not api_key:
        raise UnauthorizedError("Missing API key.")
    valid_keys = settings.valid_api_keys_set
    if settings.ENVIRONMENT == "local" and not valid_keys:
        # Convenience for local dev only; never falls through in staging/production.
        return ClientIdentity(client_id="local-dev")
    if api_key not in valid_keys:
        raise UnauthorizedError("Invalid API key.")
    # Use a stable hash as the client identifier for logging/rate-limit keys
    client_id = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    return ClientIdentity(client_id=client_id)


async def rate_limiter(request: Request, client: ClientIdentity = Depends(get_current_client)) -> None:
    """Fixed-window rate limiter backed by Redis INCR + EXPIRE."""
    redis = get_redis()
    window = int(time.time() // 60)
    key = f"ratelimit:{client.client_id}:{window}"
    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, 60)
    if current > settings.RATE_LIMIT_PER_MINUTE:
        raise RateLimitError(
            f"Rate limit of {settings.RATE_LIMIT_PER_MINUTE} requests/minute exceeded.",
            details={"retry_after_seconds": 60 - (int(time.time()) % 60)},
        )


def verify_webhook_signature(payload_body: bytes, signature_header: str | None) -> bool:
    """
    Verifies inbound provider webhook signatures using HMAC-SHA256, timing-safe.
    Providers (Twilio, SendGrid, custom) typically send a signature header;
    this generic verifier can be adapted per-provider.
    """
    if not signature_header:
        return False
    expected = hmac.new(
        settings.WEBHOOK_HMAC_SECRET.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


async def verify_webhook(request: Request, x_signature: str | None = Header(default=None)) -> None:
    body = await request.body()
    if not verify_webhook_signature(body, x_signature):
        raise UnauthorizedError("Invalid webhook signature.")