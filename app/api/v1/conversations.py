from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ClientIdentity, get_current_client
from app.models.conversation import ConversationStatus
from app.schemas.common import Page
from app.schemas.conversation import ConversationCreate, ConversationRead, ConversationStatusSummary
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("/", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    client: ClientIdentity = Depends(get_current_client),
):
    service = ConversationService(db)
    conversation = await service.create(payload, created_by=client.client_id)
    return conversation


@router.get("/", response_model=Page[ConversationRead])
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: ConversationStatus | None = None,
    db: AsyncSession = Depends(get_db),
    _: ClientIdentity = Depends(get_current_client),
):
    service = ConversationService(db)
    conversations, total = await service.list(limit=limit, offset=offset, status=status)
    return Page(
        items=[ConversationRead.model_validate(item) for item in conversations],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{conversation_id}", response_model=ConversationRead)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: ClientIdentity = Depends(get_current_client),
):
    service = ConversationService(db)
    return await service.get(conversation_id)


@router.get("/{conversation_id}/status", response_model=ConversationStatusSummary)
async def get_conversation_status(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: ClientIdentity = Depends(get_current_client),
):
    service = ConversationService(db)
    return await service.get_status_summary(conversation_id)
