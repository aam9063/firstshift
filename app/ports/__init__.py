"""Port interfaces to the client systems (architecture rule 2).

Each port is a Protocol; mocks (mocks/) and real adapters (app/adapters/)
implement the same contract, so swapping a mock for a real adapter is
configuration, not code.
"""

from app.ports.hiredesk import HireDeskPort, StageUpdate
from app.ports.messaging import MessagingChannelPort, OutboundMessage

__all__ = [
    "HireDeskPort",
    "MessagingChannelPort",
    "OutboundMessage",
    "StageUpdate",
]
