import logging
import uuid

import httpx

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import db_session_ctx, run_worker_coroutine
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.services.notification_service import send_completion_webhook

logger = logging.getLogger("app.workers.notify")


async def _notify(conversation_id: str) -> None:
    async with db_session_ctx() as db:
        conversation_repo = ConversationRepository(db)
        message_repo = MessageRepository(db)

        conversation = await conversation_repo.get_by_id(uuid.UUID(conversation_id))
        if conversation is None:
            logger.warning("notify_conversation_not_found", extra={"path": conversation_id})
            return
        if not conversation.notification_webhook_url:
            return  # client didn't register a webhook; nothing to do

        counts = await message_repo.status_counts_for_conversation(conversation.id)
        payload = {
            "event": "conversation.completed",
            "conversation_id": str(conversation.id),
            "status": conversation.status.value,
            "completed_at": conversation.completed_at.isoformat() if conversation.completed_at else None,
            "message_counts": {status.value: count for status, count in counts.items()},
        }
        await send_completion_webhook(conversation.notification_webhook_url, payload)


@celery_app.task(
    name="app.workers.tasks_notify.notify_conversation_completed",
    bind=True,
    max_retries=None,  # governed by settings.NOTIFICATION_MAX_RETRIES below
)
def notify_conversation_completed(self, conversation_id: str) -> None:
    """
    Fires exactly once conversation processing fully completes (all messages
    terminal). Retries with exponential backoff on delivery failure so a
    temporarily-down client endpoint doesn't lose the notification; gives up
    after NOTIFICATION_MAX_RETRIES and logs loudly for operator follow-up
    (in production, also push to a dead-letter alerting queue here).
    """
    try:
        run_worker_coroutine(lambda: _notify(conversation_id))
    except httpx.HTTPError as exc:
        if self.request.retries >= settings.NOTIFICATION_MAX_RETRIES:
            logger.error(
                "notification_delivery_permanently_failed",
                extra={"path": conversation_id, "error_code": str(exc)},
            )
            return
        backoff = 10 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=backoff)
    except Exception:
        logger.exception("notification_task_unexpected_error", extra={"path": conversation_id})
        raise