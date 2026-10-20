"""MessagingChannelPort: the conversation channel (integration-contracts §7).

One port, two adapters (architecture rule 2): the in-process simulator
adapter (default, app/adapters/simulator.py) and the Twilio WhatsApp adapter
(the governed channel, later feature). Delivery is outbox-relayed like every
write; the C-T5 idempotency key scheme for outbound messages is
fs/whatsapp/send/{restaurant_id}/{object_id}/{outbox_message_id}.
"""

from typing import Protocol

from pydantic import BaseModel, Field


class OutboundMessage(BaseModel):
    """Payload of one outbound channel message."""

    recipient_ref: str  # channel-scoped phone
    body: str  # candidate language, never mixed
    quick_replies: list[str] = Field(default_factory=list, max_length=3)  # C-O2
    correlation_id: str  # event stream id, visible in the console


class MessagingChannelPort(Protocol):
    """Contract every channel adapter implements.

    ``verify_webhook`` and ``handle_inbound`` arrive with the Twilio adapter
    (F07): inbound messages are deduplicated on ``provider_message_id``.
    """

    def send_message(self, payload: OutboundMessage) -> None:
        """Deliver one outbound message."""
        ...
