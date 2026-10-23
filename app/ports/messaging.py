"""MessagingChannelPort: the conversation channel (integration-contracts §7).

One port, two adapters (architecture rule 2): the in-process simulator
adapter (default, app/adapters/simulator.py) and the Twilio WhatsApp adapter
(the governed channel). Delivery is outbox-relayed like every write; the
C-T5 idempotency key scheme for outbound messages is
fs/whatsapp/send/{restaurant_id}/{object_id}/{outbox_message_id}.

WhatsApp channel hardening (specs/06 §1): the 24h customer service window
and pre-approved templates for messages outside it, delivery and read
receipts, and opt-out keywords. The window and template policy lives on the
Twilio adapter (channel specifics); the port carries the shared shapes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field


class OutboundMessage(BaseModel):
    """Payload of one outbound channel message."""

    recipient_ref: str  # channel-scoped phone
    body: str  # candidate language, never mixed
    quick_replies: list[str] = Field(default_factory=list, max_length=3)  # C-O2
    correlation_id: str  # event stream id, visible in the console


class InboundMessage(BaseModel):
    """One inbound channel message; the provider id is the idempotency key."""

    provider_message_id: str
    sender_ref: str
    body: str
    received_at: datetime
    quick_reply_id: str | None = None  # one-tap manager decisions (ADR-004)


class MessagingChannelPort(Protocol):
    """Contract every channel adapter implements.

    ``verify_webhook`` and ``handle_inbound`` are implemented by the Twilio
    adapter (twilio-channel): inbound messages are deduplicated on
    ``provider_message_id``.
    """

    def send_message(self, payload: OutboundMessage) -> None:
        """Deliver one outbound message."""
        ...


__all__ = ["InboundMessage", "MessagingChannelPort", "OutboundMessage"]
