from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from app.models.message import MessageChannel


class ProviderOutcome(str, Enum):
    ACCEPTED = "accepted"    
    REJECTED = "rejected"    
    TRANSIENT_ERROR = "transient_error" 


@dataclass
class ProviderSendResult:
    outcome: ProviderOutcome
    provider_message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class MessageProviderBase(ABC):
    name: str = "base"

    @abstractmethod
    async def send(
        self,
        *,
        channel: MessageChannel,
        to_address: str,
        content: str,
    ) -> ProviderSendResult:

        raise NotImplementedError


class ProviderError(Exception):
    """Raised for unexpected provider client errors (bugs, bad config)."""