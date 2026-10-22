"""Twilio WhatsApp channel adapter (twilio-channel T2, S2/S3).

The governed MessagingChannelPort adapter (integration-contracts section 7):
outbound replies are delivered to the Twilio REST API (2010-04-01 Messages
resource) with the subaccount API key (SID + secret as basic auth), so
credentials can be revoked per project without touching the parent account
(S2; credits draw from the parent balance).

The base URL is the production Twilio API (https://api.twilio.com); tests
mock it with respx, so no test traffic ever reaches Twilio.

Delivery failures follow the contract error semantics: carrier-level
problems (5xx, 429, timeouts, connection errors) raise
TwilioChannelTransientError and are retried by the relay; a rejected request
(4xx) raises TwilioChannelRejectedError and must never be retried (a broken
conversation cannot be spammed).
"""

from __future__ import annotations

import httpx

from app.adapters.simulator import InMemorySimulatorChannel
from app.ports.messaging import OutboundMessage
from app.settings import settings

TWILIO_BASE_URL = "https://api.twilio.com"
DEFAULT_TIMEOUT_SECONDS = 10.0


class TwilioChannelError(RuntimeError):
    """Base class for Twilio channel adapter failures."""


class TwilioChannelTransientError(TwilioChannelError):
    """Retryable delivery failure (carrier level)."""


class TwilioChannelRejectedError(TwilioChannelError):
    """Permanent rejection (bad number, sandbox not joined): never retried."""


class TwilioChannelAdapter:
    """Sends one outbound WhatsApp message through the Twilio REST API."""

    def __init__(
        self,
        *,
        account_sid: str,
        api_key_sid: str,
        api_key_secret: str,
        whatsapp_from: str,
        base_url: str = TWILIO_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._account_sid = account_sid
        self._api_key_sid = api_key_sid
        self._api_key_secret = api_key_secret
        self._whatsapp_from = whatsapp_from
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def send_message(self, payload: OutboundMessage) -> str:
        """Deliver one message and return the provider MessageSid.

        The port protocol declares ``None``; this adapter returns the
        provider id because the outbox relay records it as the delivery
        receipt and inbound dedup is keyed on provider message ids (S3).
        """
        to = payload.recipient_ref
        if not to.startswith("whatsapp:"):
            to = f"whatsapp:{to}"
        try:
            response = httpx.post(
                f"{self._base_url}/2010-04-01/Accounts/{self._account_sid}/Messages.json",
                data={"From": self._whatsapp_from, "To": to, "Body": payload.body},
                auth=(self._api_key_sid, self._api_key_secret),
                timeout=self._timeout_seconds,
            )
        except httpx.TransportError as exc:
            raise TwilioChannelTransientError(
                f"twilio rest unreachable: {exc}"
            ) from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise TwilioChannelTransientError(
                f"twilio transient failure: {response.status_code}"
            )
        if response.status_code >= 400:
            raise TwilioChannelRejectedError(
                f"twilio rejected the message: {response.status_code}"
            )
        sid = response.json().get("sid")
        if not sid:
            raise TwilioChannelError("twilio response without a sid")
        return str(sid)


def select_whatsapp_channel() -> TwilioChannelAdapter | InMemorySimulatorChannel:
    """The whatsapp-port adapter, selected by configuration, not code
    (architecture rule 2): Twilio when the subaccount credentials are set,
    the in-process simulator adapter otherwise (the default for tests and
    demos)."""
    if (
        settings.twilio_account_sid
        and settings.twilio_api_key_sid
        and settings.twilio_api_key_secret
    ):
        return TwilioChannelAdapter(
            account_sid=settings.twilio_account_sid,
            api_key_sid=settings.twilio_api_key_sid,
            api_key_secret=settings.twilio_api_key_secret,
            whatsapp_from=settings.twilio_whatsapp_from,
        )
    from app.adapters.simulator import channel as simulator_channel

    return simulator_channel
