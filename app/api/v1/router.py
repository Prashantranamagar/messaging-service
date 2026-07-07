from fastapi import APIRouter

from app.api.v1 import conversations, messages, recipients, webhooks

api_router = APIRouter()
api_router.include_router(recipients.router)
api_router.include_router(conversations.router)
api_router.include_router(messages.router)
api_router.include_router(webhooks.router)