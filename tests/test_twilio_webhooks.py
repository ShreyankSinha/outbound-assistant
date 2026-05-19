from __future__ import annotations

import pytest
from starlette.testclient import TestClient
from twilio.request_validator import RequestValidator

from app.api import fastapi_app as fa
from app.config import get_settings
from app.core.enums import CallState, ConversationState, SessionOutcome
from app.schemas.parsed_intent import ParsedIntent
from app.schemas.session_state import SessionState


def _session() -> SessionState:
    intent = ParsedIntent(raw_instruction="x", customer_id=1, issue_type="overdue_invoice", desired_resolution="pay")
    return SessionState(
        session_id="s-webhook",
        timestamp_start="2026-01-01T00:00:00Z",
        operator_instruction="x",
        parsed_intent=intent,
        call_target="+15551111",
        call_control_id="CA_hook",
        call_state=CallState.RINGING,
        conversation_state=ConversationState.UNDERSTANDING,
        twilio_gather_action_url_absolute="https://example.com/webhooks/twilio/action",
        twilio_voice_url_absolute="https://example.com/webhooks/twilio/voice",
        twilio_status_callback_url_absolute="https://example.com/webhooks/twilio/status",
    )


@pytest.fixture()
def twilio_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def mock_sig(*args, **kwargs): pass
    monkeypatch.setattr("app.api.routes_twilio_webhooks._require_valid_twilio_signature", mock_sig)
    get_settings.cache_clear()
    return TestClient(fa.app)


@pytest.mark.parametrize(
    ("status", "expected_call_state"),
    [
        ("initiated", CallState.RINGING),
        ("queued", CallState.RINGING),
        ("ringing", CallState.RINGING),
        ("in-progress", CallState.ANSWERED),
        ("completed", CallState.ENDED),
        ("failed", CallState.FAILED),
        ("busy", CallState.ENDED),
        ("no-answer", CallState.ENDED),
    ],
)
def test_status_callback_transitions(
    twilio_client: TestClient, monkeypatch: pytest.MonkeyPatch, status: str, expected_call_state: CallState
) -> None:
    async def mock_sig(*args, **kwargs): pass
    monkeypatch.setattr("app.api.routes_twilio_webhooks._require_valid_twilio_signature", mock_sig)
    get_settings.cache_clear()
    fa.registry.clear()
    fa.registry.save(_session())
    twilio_client.post("/webhooks/twilio/status", data={"CallSid": "CA_hook", "CallStatus": status})
    updated = fa.registry.get("s-webhook")
    assert updated is not None
    assert updated.call_state == expected_call_state


def test_invalid_signature_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_auth_token")
    get_settings.cache_clear()
    fa.registry.clear()
    fa.registry.save(_session())
    c = TestClient(fa.app)
    r = c.post("/webhooks/twilio/status", data={"CallSid": "CA_hook", "CallStatus": "ringing"})
    assert r.status_code == 403


def test_voicemail_amd_machine_end_beep_sets_no_answer(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    async def mock_sig(*args, **kwargs): pass
    monkeypatch.setattr("app.api.routes_twilio_webhooks._require_valid_twilio_signature", mock_sig)
    get_settings.cache_clear()
    fa.registry.clear()
    fa.registry.save(_session())
    fa.session_service.persistence.log_dir = tmp_path

    c = TestClient(fa.app)
    c.post(
        "/webhooks/twilio/status",
        data={"CallSid": "CA_hook", "CallStatus": "in-progress", "AnsweredBy": "machine_end_beep"},
    )
    c.post("/webhooks/twilio/status", data={"CallSid": "CA_hook", "CallStatus": "completed"})

    updated = fa.registry.get("s-webhook")
    assert updated is not None
    assert updated.call_state == CallState.ENDED
    assert updated.outcome == SessionOutcome.NO_ANSWER


def test_valid_signature_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "mytoken")
    get_settings.cache_clear()
    fa.registry.clear()
    fa.registry.save(_session())

    url = "http://testserver/webhooks/twilio/status"
    params = {"CallSid": "CA_hook", "CallStatus": "ringing"}
    sig = RequestValidator("mytoken").compute_signature(url, params)

    c = TestClient(fa.app)
    r = c.post("/webhooks/twilio/status", data=params, headers={"X-Twilio-Signature": sig})
    assert r.status_code == 200
