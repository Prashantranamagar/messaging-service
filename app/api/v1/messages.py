from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ClientIdentity, get_current_client
from app.schemas.common import MessageResponse, Page
from app.schemas.message import MessageRead, SendMessageRequest, SendMessageResponse
from app.services.message_service import MessageService

router = APIRouter(prefix="/conversations/{conversation_id}/messages", tags=["messages"])


@router.post("/", response_model=SendMessageResponse, status_code=status.HTTP_201_CREATED)
async def send_messages_to_conversation(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    _: ClientIdentity = Depends(get_current_client),
):
    service = MessageService(db)
    messages, rejected_recipients = await service.send_to_recipients(conversation_id, payload)
    return SendMessageResponse(
        conversation_id=conversation_id,
        messages=[MessageRead.model_validate(message) for message in messages],
        accepted_count=len(messages),
        rejected_recipients=rejected_recipients,
    )


@router.get("/", response_model=Page[MessageRead])
async def list_messages_for_conversation(
    conversation_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: ClientIdentity = Depends(get_current_client),
):
    service = MessageService(db)
    messages, total = await service.list_by_conversation(conversation_id, limit=limit, offset=offset)
    return Page(
        items=[MessageRead.model_validate(message) for message in messages],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{message_id}", response_model=MessageRead)
async def get_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: ClientIdentity = Depends(get_current_client),
):
    del conversation_id
    service = MessageService(db)
    return await service.get(message_id)


@router.post("/{message_id}/delivery-status", response_model=MessageResponse)
async def delivery_status_for_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: ClientIdentity = Depends(get_current_client),
):
    del conversation_id, message_id
    return MessageResponse(message="Delivery status updates are handled via webhook callbacks.")
