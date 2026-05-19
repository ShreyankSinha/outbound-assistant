from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from twilio.base.exceptions import TwilioRestException

from app.core.enums import CallState, ConversationState
from app.core.exceptions import ProviderError
from app.schemas.parsed_intent import ParsedIntent
from app.schemas.session_state import SessionState
from app.services.session_registry import SessionRegistry
from app.services.session_service import SessionService
from app.transport.gradio_transport import GradioTransport
from app.transport.twilio.outbound_call import TwilioOutboundCall
from app.transport.twilio_transport import TwilioTransport


def _minimal_session() -> SessionState:
    intent = ParsedIntent(
        raw_instruction="test",
        customer_id=1,
        customer_name="Test",
        phone_number="+15550001",
        issue_type="overdue_invoice",
        desired_resolution="collect payment",
        amount="$100",
    )
    return SessionState(
        session_id="sess-1",
        timestamp_start="2026-01-01T00:00:00Z",
        operator_instruction="test",
        parsed_intent=intent,
        call_target="+15550002",
        call_state=CallState.RINGING,
        twilio_voice_url_absolute="https://example.com/webhooks/twilio/voice",
        twilio_status_callback_url_absolute="https://example.com/webhooks/twilio/status",
    )


def test_outbound_call_create_uses_amd_and_async_amd() -> None:
    with (
        patch("app.transport.twilio.outbound_call.get_settings") as mock_gs,
        patch("app.transport.twilio.outbound_call.Client") as mock_client_cls,
    ):
        mock_gs.return_value = MagicMock(
            twilio_account_sid="ACxxx",
            twilio_auth_token="token",
            twilio_phone_number="+15550000",
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_call = MagicMock()
        mock_call.sid = "CA_test_sid"
        mock_call.status = "queued"
        mock_client.calls.create.return_value = mock_call

        ob = TwilioOutboundCall()
        ob.create_outbound_call(
            to_number="+15550002",
            session_id="sess-1",
            voice_url_absolute="https://example.com/webhooks/twilio/voice",
            status_callback_url="https://example.com/webhooks/twilio/status",
            async_amd_status_callback_url="https://example.com/webhooks/twilio/status",
        )

        mock_client.calls.create.assert_called_once()
        kwargs = mock_client.calls.create.call_args.kwargs
        assert kwargs["to"] == "+15550002"
        assert kwargs["from_"] == "+15550000"
        assert kwargs["machine_detection"] == "Enable"
        assert kwargs["async_amd"] == "true"
        assert kwargs["status_callback"] == "https://example.com/webhooks/twilio/status"
        assert "session_id=sess-1" in kwargs["url"]


@pytest.mark.asyncio
async def test_twilio_transport_maps_4xx_to_failed_state() -> None:
    transport = TwilioTransport()
    session = _minimal_session()
    with patch.object(
        transport.outbound,
        "create_outbound_call",
        side_effect=TwilioRestException(400, "https://api.twilio.com", "Bad Request"),
    ):
        with pytest.raises(ProviderError):
            await transport.start_session(session)
    assert session.call_state == CallState.FAILED
    assert session.errors


@pytest.mark.asyncio
async def test_amd_machine_start_sets_voicemail_on_session_via_service() -> None:
    service = SessionService(GradioTransport(), SessionRegistry())
    session = _minimal_session()
    session.call_control_id = "CA_amd"
    service.registry.save(session)

    await service.handle_twilio_status({"CallSid": "CA_amd", "CallStatus": "ringing", "AnsweredBy": "machine_start"})
    updated = service.registry.get("sess-1")
    assert updated is not None
    assert updated.call_state == CallState.VOICEMAIL_DETECTED
    assert updated.conversation_state == ConversationState.VOICEMAIL


@pytest.mark.asyncio
async def test_amd_human_moves_toward_active() -> None:
    service = SessionService(GradioTransport(), SessionRegistry())
    session = _minimal_session()
    session.call_control_id = "CA_human"
    session.call_state = CallState.RINGING
    service.registry.save(session)

    await service.handle_twilio_status({"CallSid": "CA_human", "CallStatus": "in-progress", "AnsweredBy": "human"})
    updated = service.registry.get("sess-1")
    assert updated is not None
    assert updated.call_state == CallState.ACTIVE
