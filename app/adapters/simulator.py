"""In-process simulator channel adapter: the default MessagingChannelPort.

No HTTP and no external dependencies (integration-contracts §7): sent
messages are recorded in memory, in order, and surfaced through
GET /simulator/messages for F06. The console consumes the persisted
message.out events later; the Twilio WhatsApp adapter replaces this adapter
by configuration in a later feature.
"""

from app.ports.messaging import OutboundMessage


class InMemorySimulatorChannel:
    """Records every ``send_message`` call in delivery order."""

    def __init__(self) -> None:
        self.sent: list[OutboundMessage] = []

    def send_message(self, payload: OutboundMessage) -> None:
        self.sent.append(payload)


channel = InMemorySimulatorChannel()
