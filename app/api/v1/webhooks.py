from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import UnauthorizedError
from app.core.security import verify_webhook_signature
from app.schemas.common import MessageResponse
from app.schemas.message import DeliveryWebhookPayload
from app.services.message_service import MessageService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/delivery-status", response_model=MessageResponse)
async def delivery_status_webhook(
    request: Request,
    payload: DeliveryWebhookPayload,
    x_signature: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Webhook endpoint that receives delivery status updates from the SMS provider.

    - Verifies the request using the HMAC signature in the `X-Signature` header.
    - Updates the message status (e.g., sent → delivered/failed).
    - Handles duplicate webhooks safely by ignoring already processed messages.(Idempotent)

    """
    raw_body = await request.body()
    signature_header = request.headers.get("X-Signature") or x_signature
    if not verify_webhook_signature(raw_body, signature_header):
        raise UnauthorizedError("Invalid webhook signature.")

    service = MessageService(db)
    await service.handle_delivery_webhook(payload)
    return MessageResponse(message="Delivery status processed.")