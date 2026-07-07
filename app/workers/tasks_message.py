import logging
import uuid
from datetime import datetime, timezone

from celery.exceptions import MaxRetriesExceededError

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import db_session_ctx, run_worker_coroutine
from app.models.conversation import ConversationStatus
from app.models.message import Message, MessageStatus, MessageStatusEvent
from app.providers.base import ProviderOutcome
from app.providers.mock_provider import get_provider
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.recipient_repo import RecipientRepository
from app.workers.tasks_notify import notify_conversation_completed

logger = logging.getLogger("app.workers.message")


async def _mark_exhausted_as_failed(message_id: str) -> None:
    """Called once retries are exhausted for a transient-error message so it
    doesn't stay stuck in an ambiguous non-terminal state forever."""
    async with db_session_ctx() as db:
        message_repo = MessageRepository(db)
        conversation_repo = ConversationRepository(db)
        message = await message_repo.get_locked_for_update(uuid.UUID(message_id))
        if message is None or message.status in MessageStatus.terminal_statuses():
            return
        message.status = MessageStatus.FAILED
        await message_repo.add_status_event(
            MessageStatusEvent(
                message_id=message.id, status=MessageStatus.FAILED, reason="retries_exhausted"
            )
        )
        await db.commit()

        if await message_repo.is_conversation_fully_terminal(message.conversation_id):
            conversation = await conversation_repo.get_by_id(message.conversation_id)
            if conversation and conversation.status not in (ConversationStatus.COMPLETED, ConversationStatus.FAILED):
                counts = await message_repo.status_counts_for_conversation(message.conversation_id)
                all_failed = counts.get(MessageStatus.DELIVERED, 0) == 0 and counts.get(MessageStatus.SENT, 0) == 0
                conversation.status = ConversationStatus.FAILED if all_failed else ConversationStatus.COMPLETED
                conversation.completed_at = datetime.now(timezone.utc)
                await db.commit()
                notify_conversation_completed.delay(str(conversation.id))


async def _dispatch(message_id: str) -> None:
    async with db_session_ctx() as db:
        message_repo = MessageRepository(db)
        recipient_repo = RecipientRepository(db)
        conversation_repo = ConversationRepository(db)

        message: Message | None = await message_repo.get_locked_for_update(uuid.UUID(message_id))
        if message is None:
            logger.warning("dispatch_message_not_found", extra={"path": message_id})
            return
        if message.status in MessageStatus.terminal_statuses():
            return  # already finalized (e.g. duplicate task delivery); nothing to do

        recipient = await recipient_repo.get_by_id(message.recipient_id, include_deleted=True)
        if recipient is None:
            await message_repo.add_status_event(
                MessageStatusEvent(message_id=message.id, status=MessageStatus.FAILED, reason="recipient_missing")
            )
            message.status = MessageStatus.FAILED
            message.error_code = "recipient_missing"
            await db.flush()
        else:
            address = recipient.phone_number if message.channel.value in ("sms", "whatsapp") else recipient.email
            message.status = MessageStatus.SENDING
            message.attempt_count += 1
            await db.flush()

            provider = get_provider(settings.PROVIDER_NAME)
            result = await provider.send(channel=message.channel, to_address=address or "", content=message.content)

            if result.outcome == ProviderOutcome.ACCEPTED:
                message.status = MessageStatus.SENT
                message.provider_name = provider.name
                message.provider_message_id = result.provider_message_id
                message.sent_at = datetime.now(timezone.utc)
                await message_repo.add_status_event(
                    MessageStatusEvent(message_id=message.id, status=MessageStatus.SENT, reason=None)
                )
            elif result.outcome == ProviderOutcome.REJECTED:
                message.status = MessageStatus.FAILED
                message.error_code = result.error_code
                message.error_message = result.error_message
                await message_repo.add_status_event(
                    MessageStatusEvent(
                        message_id=message.id, status=MessageStatus.FAILED, reason=result.error_message
                    )
                )
            else:  # TRANSIENT_ERROR
                message.error_code = result.error_code
                message.error_message = result.error_message
                await db.flush()
                await db.commit()
                raise _TransientProviderError(result.error_message or "transient provider error")

            await db.flush()

        await db.commit()

        # Check whether the whole conversation is now fully terminal; if so,
        # flip conversation status and enqueue the completion notification.
        # This check is cheap (single GROUP BY query) and safe to run after
        # every message update — at-most a little redundant work under
        # concurrency, never a missed notification.
        if await message_repo.is_conversation_fully_terminal(message.conversation_id):
            conversation = await conversation_repo.get_by_id(message.conversation_id)
            if conversation and conversation.status not in (ConversationStatus.COMPLETED, ConversationStatus.FAILED):
                counts = await message_repo.status_counts_for_conversation(message.conversation_id)
                all_failed = counts.get(MessageStatus.DELIVERED, 0) == 0 and counts.get(MessageStatus.SENT, 0) == 0
                new_status = ConversationStatus.FAILED if all_failed else ConversationStatus.COMPLETED
                conversation.status = new_status
                conversation.completed_at = datetime.now(timezone.utc)
                await db.commit()
                notify_conversation_completed.delay(str(conversation.id))


class _TransientProviderError(Exception):
    """Internal signal used to trigger Celery's retry path for transient
    provider failures (timeouts, 5xx) without conflating them with permanent
    rejections, which are terminal by design."""


@celery_app.task(
    name="app.workers.tasks_message.dispatch_message",
    bind=True,
    max_retries=settings.MESSAGE_SEND_MAX_RETRIES,
)
def dispatch_message(self, message_id: str) -> None:
    try:
        run_worker_coroutine(lambda: _dispatch(message_id))
    except _TransientProviderError as exc:
        backoff = settings.MESSAGE_SEND_RETRY_BACKOFF * (2 ** self.request.retries)
        try:
            logger.warning(
                "message_dispatch_transient_failure_retrying",
                extra={"path": message_id, "latency_ms": backoff},
            )
            raise self.retry(exc=exc, countdown=backoff)
        except MaxRetriesExceededError:
            logger.error("message_dispatch_retries_exhausted", extra={"path": message_id})
            run_worker_coroutine(lambda: _mark_exhausted_as_failed(message_id))
    except Exception:
        logger.exception("message_dispatch_failed_unexpectedly", extra={"path": message_id})
        raise


async def _sweep_stale_queued() -> list[str]:
    """
    Finds messages that have sat in QUEUED for longer than a grace period
    and re-enqueues them.

    Why this exists: the API commits the Message row *then* calls
    `dispatch_message.delay(...)`. If the broker is briefly unreachable
    between those two steps (deploy, network blip, Redis failover), the
    message is durably persisted but the dispatch task is silently lost —
    it would otherwise stay QUEUED forever with no worker ever picking it
    up. This periodic sweep (wired to Celery Beat) is the recovery path.
    Safe to run concurrently with normal dispatch because dispatch_message
    re-checks status under a row lock and is a no-op if already terminal.
    """
    from datetime import timedelta

    from sqlalchemy import select

    grace_period = timedelta(minutes=5)
    cutoff = datetime.now(timezone.utc) - grace_period

    async with db_session_ctx() as db:
        result = await db.execute(
            select(Message.id).where(Message.status == MessageStatus.QUEUED, Message.created_at < cutoff)
        )
        stale_ids = [str(row[0]) for row in result.all()]

    return stale_ids


@celery_app.task(name="app.workers.tasks_message.sweep_stale_queued_messages")
def sweep_stale_queued_messages() -> int:
    stale_ids = run_worker_coroutine(_sweep_stale_queued)
    for message_id in stale_ids:
        dispatch_message.delay(message_id)
    if stale_ids:
        logger.warning("requeued_stale_messages", extra={"path": f"count={len(stale_ids)}"})
    return len(stale_ids)