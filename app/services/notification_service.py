import hashlib
import hmac
import json
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("app.notifications")


def sign_payload(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, default=str).encode()
    return hmac.new(settings.WEBHOOK_HMAC_SECRET.encode(), body, hashlib.sha256).hexdigest()


async def send_completion_webhook(webhook_url: str, payload: dict) -> None:
    """Raises on failure so the Celery task's retry policy takes over."""
    signature = sign_payload(payload)
    async with httpx.AsyncClient(timeout=settings.NOTIFICATION_WEBHOOK_TIMEOUT_SECONDS) as client:
        response = await client.post(
            webhook_url,
            json=payload,
            headers={"X-Signature": signature, "Content-Type": "application/json"},
        )
        response.raise_for_status()
        logger.info(
            "conversation_completion_webhook_delivered",
            extra={"path": webhook_url, "status_code": response.status_code},
        )