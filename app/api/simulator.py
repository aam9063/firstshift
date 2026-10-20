"""Simulator API (F06): lists the messages the simulator channel recorded.

The console consumes the persisted message.out events later; this read-only
endpoint is enough to see what the in-process adapter sent.
"""

from typing import Any

from fastapi import APIRouter

from app.adapters.simulator import channel

router = APIRouter(prefix="/simulator", tags=["simulator"])


@router.get("/messages")
def list_messages() -> list[dict[str, Any]]:
    return [message.model_dump() for message in channel.sent]
