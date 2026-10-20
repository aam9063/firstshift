"""HireDeskPort: the ATS (integration-contracts §1).

FirstShift's own record is authoritative; HireDesk is mirrored for Talent
reporting. Outbound stage writes go through the outbox and the relay worker
(S5); the mock adapter (mocks/services/routers/hiredesk.py) implements the
same contract the real adapter will.
"""

from typing import Literal, Protocol

from pydantic import BaseModel


class StageUpdate(BaseModel):
    """Stage write back to HireDesk, linked to a human Decision record (C-L6)."""

    hiredesk_application_id: str
    stage: Literal["screening", "interview", "offer", "hired", "rejected"]
    rejection_reason: str | None = None  # rejections stop disappearing [T-jordi-18]
    decision_id: str


class HireDeskPort(Protocol):
    """Contract for the ATS adapter; ``create_requisition`` and friends arrive
    with the features that need them."""

    def update_stage(self, payload: StageUpdate) -> None:
        """Mirror a stage change into HireDesk (outbox-relayed, S5)."""
        ...
