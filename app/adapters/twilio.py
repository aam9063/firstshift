"""Twilio WhatsApp channel adapter (twilio-channel T2, S2/S3; F12 S1).

The governed MessagingChannelPort adapter (integration-contracts section 7):
outbound replies are delivered to the Twilio REST API (2010-04-01 Messages
resource) with the subaccount API key (SID + secret as basic auth), so
credentials can be revoked per project without touching the parent account
(S2; credits draw from the parent balance).

The base URL is the production Twilio API (https://api.twilio.com); tests
mock it with respx, so no test traffic ever reaches Twilio.

Hardened failure modes (specs/06 section 1, WhatsApp row):

- 24h customer service window: free-form sends are only allowed within 24
  hours of the recipient's last inbound message; outside the window a
  pre-approved template is required, otherwise TwilioChannelWindowClosedError
  stops the send before it can fail at the carrier.
- Templates: ``send_message(..., template=...)`` posts the ContentSid and
  content variables for sends outside the window.
- Opt-out keywords (EN and ES): an inbound STOP/ALTO/BAJA/... marks the
  recipient opted out and every further send is rejected.
- Delivery and read receipts: status callbacks are recorded per provider
  message sid (``handle_status_callback`` / ``receipt_status``).

Delivery failures follow the contract error semantics: carrier-level
problems (5xx, 429, timeouts, connection errors) raise
TwilioChannelTransientError and are retried by the relay; a rejected request
(4xx) raises TwilioChannelRejectedError and must never be retried (a broken
conversation cannot be spammed).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel

from app.adapters.simulator import InMemorySimulatorChannel
from app.ports.messaging import InboundMessage, OutboundMessage
from app.settings import settings

TWILIO_BASE_URL = "https://api.twilio.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
CUSTOMER_SERVICE_WINDOW = timedelta(hours=24)  # WhatsApp 24h rule

# Twilio's standard WhatsApp opt-out keywords plus the Spanish ones the
# candidates actually use (docs/integration-guide.md, WhatsApp section).
OPT_OUT_KEYWORDS = frozenset(
    {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "ALTO", "BAJA", "DAR DE BAJA"}
)


def _basic_auth_for(
    account_sid: str,
    api_key_sid: str | None,
    api_key_secret: str | None,
    auth_token: str | None,
) -> tuple[str, str]:
    """API-key auth (SK sid + secret) when present; account auth otherwise.

    Both authenticate the same REST API; API keys are the recommended
    credential for subaccounts, but the account SID + auth token pair is
    equally valid and is what a minimal sandbox setup has on hand.
    """
    if api_key_sid and api_key_secret:
        return (api_key_sid, api_key_secret)
    if auth_token:
        return (account_sid, auth_token)
    raise TwilioChannelError(
        "twilio credentials missing: set TWILIO_API_KEY_SID + SECRET, or TWILIO_AUTH_TOKEN"
    )


class TwilioChannelError(RuntimeError):
    """Base class for Twilio channel adapter failures."""


class TwilioChannelTransientError(TwilioChannelError):
    """Retryable delivery failure (carrier level)."""


class TwilioChannelRejectedError(TwilioChannelError):
    """Permanent rejection (bad number, opted out, sandbox not joined): never
    retried."""


class TwilioChannelWindowClosedError(TwilioChannelRejectedError):
    """Free-form send outside the 24h customer service window; convert to a
    pre-approved template send instead."""


class TemplateMessage(BaseModel):
    """A pre-approved WhatsApp template (registered in the Twilio account)."""

    content_sid: str
    variables: dict[str, str] = {}


def _normalize_recipient(recipient_ref: str) -> str:
    return recipient_ref.removeprefix("whatsapp:")


class TwilioChannelAdapter:
    """Sends one outbound WhatsApp message through the Twilio REST API."""

    def __init__(
        self,
        *,
        account_sid: str,
        api_key_sid: str | None,
        api_key_secret: str | None,
        auth_token: str | None,
        whatsapp_from: str,
        base_url: str = TWILIO_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._account_sid = account_sid
        self._basic_auth = _basic_auth_for(
            account_sid, api_key_sid, api_key_secret, auth_token
        )
        self._whatsapp_from = whatsapp_from
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._now = now or (lambda: datetime.now(UTC))
        self._last_inbound_at: dict[str, datetime] = {}
        self._opted_out: set[str] = set()
        self._receipts: dict[str, str] = {}

    # -- window and opt-out state -------------------------------------------

    def handle_inbound(self, payload: InboundMessage) -> dict[str, str]:
        """Record an inbound message: it opens the 24h window and may opt the
        recipient out (keyword in the body, EN or ES)."""

        recipient = _normalize_recipient(payload.sender_ref)
        keyword = payload.body.strip().upper()
        if keyword in OPT_OUT_KEYWORDS:
            self._opted_out.add(recipient)
            return {"status": "opted_out", "recipient": recipient}
        self._last_inbound_at[recipient] = payload.received_at
        return {"status": "received", "recipient": recipient}

    def is_opted_out(self, recipient_ref: str) -> bool:
        return _normalize_recipient(recipient_ref) in self._opted_out

    def window_open(self, recipient_ref: str) -> bool:
        """The 24h customer service window: open iff the recipient's last
        inbound message is younger than 24 hours."""

        recipient = _normalize_recipient(recipient_ref)
        last_inbound = self._last_inbound_at.get(recipient)
        if last_inbound is None:
            return False
        return self._now() - last_inbound < CUSTOMER_SERVICE_WINDOW

    # -- outbound -------------------------------------------------------------

    def send_message(
        self, payload: OutboundMessage, *, template: TemplateMessage | None = None
    ) -> str:
        """Deliver one message and return the provider MessageSid.

        The port protocol declares ``None``; this adapter returns the
        provider id because the outbox relay records it as the delivery
        receipt and inbound dedup is keyed on provider message ids (S3).
        Outside the 24h window a template is required: with one, the send
        posts the ContentSid; without one the send is refused locally so no
        carrier rejection loop can start.
        """

        if self.is_opted_out(payload.recipient_ref):
            raise TwilioChannelRejectedError(
                f"recipient {payload.recipient_ref} opted out; sends stop"
            )
        if template is None and not self.window_open(payload.recipient_ref):
            raise TwilioChannelWindowClosedError(
                f"24h window closed for {payload.recipient_ref}; use a pre-approved template"
            )

        to = payload.recipient_ref
        if not to.startswith("whatsapp:"):
            to = f"whatsapp:{to}"
        form: dict[str, str] = {"From": self._whatsapp_from, "To": to}
        if template is not None:
            form["ContentSid"] = template.content_sid
            if template.variables:
                form["ContentVariables"] = json.dumps(template.variables)
        else:
            form["Body"] = payload.body
        try:
            response = httpx.post(
                f"{self._base_url}/2010-04-01/Accounts/{self._account_sid}/Messages.json",
                data=form,
                auth=self._basic_auth,
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

    # -- receipts ---------------------------------------------------------------

    def handle_status_callback(self, form: Mapping[str, Any]) -> dict[str, str]:
        """Record a Twilio status callback (delivered, read, failed, ...)."""

        message_sid = str(form.get("MessageSid", ""))
        status = str(form.get("MessageStatus", ""))
        if not message_sid or not status:
            raise TwilioChannelError("status callback without MessageSid/MessageStatus")
        self._receipts[message_sid] = status
        return {"message_sid": message_sid, "status": status}

    def receipt_status(self, message_sid: str) -> str | None:
        """The latest receipt status recorded for a provider message id."""

        return self._receipts.get(message_sid)


def select_whatsapp_channel() -> TwilioChannelAdapter | InMemorySimulatorChannel:
    """The whatsapp-port adapter, selected by configuration, not code
    (architecture rule 2): Twilio when the subaccount credentials are set,
    the in-process simulator adapter otherwise (the default for tests and
    demos)."""
    if settings.twilio_account_sid and (
        (settings.twilio_api_key_sid and settings.twilio_api_key_secret)
        or settings.twilio_auth_token
    ):
        return TwilioChannelAdapter(
            account_sid=settings.twilio_account_sid,
            api_key_sid=settings.twilio_api_key_sid,
            api_key_secret=settings.twilio_api_key_secret,
            auth_token=settings.twilio_auth_token,
            whatsapp_from=settings.twilio_whatsapp_from,
        )
    from app.adapters.simulator import channel as simulator_channel

    return simulator_channel
