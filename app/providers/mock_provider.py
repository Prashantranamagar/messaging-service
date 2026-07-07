import asyncio
import random
import uuid

from app.models.message import MessageChannel
from app.providers.base import MessageProviderBase, ProviderOutcome, ProviderSendResult


class MockProvider(MessageProviderBase):
    """
    Mock SMS provider for development and testing.

    Simulates realistic responses with random success, failure, and retryable
    errors, without making real network requests.
    """

    name = "mock"

    async def send(self, *, channel: MessageChannel, to_address: str, content: str) -> ProviderSendResult:
        await asyncio.sleep(random.uniform(0.05, 0.2))

        if not to_address:
            return ProviderSendResult(
                outcome=ProviderOutcome.REJECTED,
                error_code="invalid_address",
                error_message="Recipient has no address for this channel.",
            )

        roll = random.random()
        if roll < 0.90:
            return ProviderSendResult(
                outcome=ProviderOutcome.ACCEPTED,
                provider_message_id=f"mock_{uuid.uuid4().hex[:16]}",
            )
        elif roll < 0.95:
            return ProviderSendResult(
                outcome=ProviderOutcome.REJECTED,
                error_code="invalid_number",
                error_message="Destination number is not reachable.",
            )
        else:
            return ProviderSendResult(
                outcome=ProviderOutcome.TRANSIENT_ERROR,
                error_code="provider_timeout",
                error_message="Upstream provider timed out.",
            )


def get_provider(provider_name: str) -> MessageProviderBase:
    """
    Provider factory. Extend with real integrations as needed:

        if provider_name == "twilio":
            return TwilioProvider(...)
        if provider_name == "sendgrid":
            return SendGridProvider(...)
    """
    if provider_name == "mock":
        return MockProvider()
    raise ValueError(f"Unknown provider: {provider_name}")