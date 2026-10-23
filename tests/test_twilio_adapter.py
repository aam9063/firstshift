"""T2 (S2, S3): TwilioChannelAdapter, the governed MessagingChannelPort adapter.

Covered here:
- send_message POSTs to the Twilio REST Messages resource with the
  subaccount API key as basic auth (SK sid + secret), From/To/Body form
  fields, and returns the provider MessageSid (respx-mocked, never real
  HTTP).
- Carrier-level failures (5xx, 429, transport errors) are transient and
  retryable; a 4xx rejection is permanent.
- The whatsapp-port adapter is selected by configuration: Twilio when the
  subaccount credentials are present, the in-process simulator otherwise
  (architecture rule 2).
"""

import base64
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from httpx import Response

from app.adapters.simulator import InMemorySimulatorChannel
from app.adapters.simulator import channel as simulator_channel
from app.adapters.twilio import (
    TWILIO_BASE_URL,
    TwilioChannelAdapter,
    TwilioChannelRejectedError,
    TwilioChannelTransientError,
    select_whatsapp_channel,
)
from app.ports.messaging import InboundMessage, OutboundMessage
from app.settings import settings

ADAPTER = TwilioChannelAdapter(
    account_sid="ACsubaccount",
    api_key_sid="SKtestkey",
    api_key_secret="testsecret",
    auth_token=None,
    whatsapp_from="whatsapp:+14155238886",
)
MESSAGES_URL = f"{TWILIO_BASE_URL}/2010-04-01/Accounts/ACsubaccount/Messages.json"


def open_window(adapter: TwilioChannelAdapter) -> None:
    """A free-form send is only allowed within the 24h customer service
    window (F12 S1); an inbound message opens it."""

    adapter.handle_inbound(
        InboundMessage(
            provider_message_id="SMin-window",
            sender_ref="+34600111222",
            body="Hola",
            received_at=datetime.now(UTC) - timedelta(hours=1),
            quick_reply_id=None,
        )
    )


def outbound() -> OutboundMessage:
    return OutboundMessage(
        recipient_ref="+34600111222",
        body="Hola: soy el asistente virtual de contratacion.",
        quick_replies=[],
        correlation_id="trace-1",
    )


@respx.mock
def test_send_message_posts_with_api_key_auth_and_returns_sid() -> None:
    route = respx.post(MESSAGES_URL).mock(
        return_value=Response(201, json={"sid": "SMfake0001"})
    )
    open_window(ADAPTER)

    sid = ADAPTER.send_message(outbound())

    assert sid == "SMfake0001"
    assert route.called
    request = route.calls.last.request
    # API key auth: SK sid + secret as basic auth (S2, subaccount setup).
    encoded = request.headers["authorization"].removeprefix("Basic ")
    assert base64.b64decode(encoded) == b"SKtestkey:testsecret"
    form = parse_qs(request.content.decode())
    assert form["From"] == ["whatsapp:+14155238886"]
    assert form["To"] == ["whatsapp:+34600111222"]
    assert form["Body"] == ["Hola: soy el asistente virtual de contratacion."]


@respx.mock
def test_transport_error_is_transient() -> None:
    respx.post(MESSAGES_URL).mock(side_effect=httpx.ConnectError("connection refused"))
    open_window(ADAPTER)

    with pytest.raises(TwilioChannelTransientError):
        ADAPTER.send_message(outbound())


@respx.mock
def test_server_error_is_transient() -> None:
    respx.post(MESSAGES_URL).mock(return_value=Response(502, text="bad gateway"))
    respx.post(MESSAGES_URL + "throttled").mock(return_value=Response(429, text="slow"))
    open_window(ADAPTER)

    with pytest.raises(TwilioChannelTransientError):
        ADAPTER.send_message(outbound())


@respx.mock
def test_client_error_is_permanent() -> None:
    respx.post(MESSAGES_URL).mock(return_value=Response(400, json={"code": 21211}))

    with pytest.raises(TwilioChannelRejectedError):
        ADAPTER.send_message(outbound())


@respx.mock
def test_account_auth_fallback_when_no_api_key() -> None:
    """A minimal subaccount setup may only have the auth token (S2): the
    adapter falls back to account SID + token basic auth."""
    route = respx.post(MESSAGES_URL).mock(
        return_value=Response(201, json={"sid": "SMfake0002"})
    )
    adapter = TwilioChannelAdapter(
        account_sid="ACsubaccount",
        api_key_sid=None,
        api_key_secret=None,
        auth_token="fallbacktoken",
        whatsapp_from="whatsapp:+14155238886",
    )
    open_window(adapter)

    sid = adapter.send_message(outbound())

    assert sid == "SMfake0002"
    encoded = route.calls.last.request.headers["authorization"].removeprefix(
        "Basic "
    )
    assert base64.b64decode(encoded) == b"ACsubaccount:fallbacktoken"


def test_selector_uses_twilio_when_subaccount_credentials_are_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "twilio_account_sid", "ACsubaccount")
    monkeypatch.setattr(settings, "twilio_api_key_sid", "SKtestkey")
    monkeypatch.setattr(settings, "twilio_api_key_secret", "testsecret")

    channel = select_whatsapp_channel()

    assert isinstance(channel, TwilioChannelAdapter)


def test_selector_falls_back_to_the_simulator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "twilio_account_sid", None)
    monkeypatch.setattr(settings, "twilio_api_key_sid", None)
    monkeypatch.setattr(settings, "twilio_api_key_secret", None)

    channel = select_whatsapp_channel()

    assert channel is simulator_channel
    assert isinstance(channel, InMemorySimulatorChannel)
