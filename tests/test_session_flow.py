import json
from pathlib import Path

import pytest

import pandas as pd

from app.services.customer_directory import CustomerDirectory
from app.services.outbound_prep_service import OutboundPrepService
from app.services.session_service import SessionService
from app.services.session_registry import SessionRegistry
from app.transport.gradio_transport import GradioTransport


@pytest.mark.asyncio
async def test_happy_path_resolves_and_persists_log(tmp_path: Path):
    service = SessionService(GradioTransport(), SessionRegistry())
    service.persistence.log_dir = tmp_path

    session = await service.create_session(
        "John Smith hasn't paid his invoice of $450 from 15 April. Follow up and get a payment commitment."
    )
    session = await service.start_session(session)
    session = await service.handle_customer_turn(session, "Okay, what's this about?")
    session = await service.handle_customer_turn(session, "Yes, I can pay tomorrow")
    session = await service.handle_customer_turn(session, "Thanks, bye.")

    assert session.outcome is not None
    assert session.outcome.value == "resolved"
    assert session.call_state.value == "ended"
    assert session.summary
    assert "log_payment_commitment" in session.summary

    log_path = tmp_path / f"{session.session_id}.json"
    assert log_path.exists()
    data = json.loads(log_path.read_text())
    assert data["outcome"] == "resolved"
    assert len(data["transcript"]) >= 5


@pytest.mark.asyncio
async def test_customer_human_request_escalates_and_persists_log(tmp_path: Path):
    service = SessionService(GradioTransport(), SessionRegistry())
    service.persistence.log_dir = tmp_path

    session = await service.create_session(
        "This customer has an overdue invoice. Call and discuss next steps."
    )
    session = await service.start_session(session)
    session = await service.handle_customer_turn(session, "I want to speak to a human")

    assert session.outcome is not None
    assert session.outcome.value == "escalated"
    assert session.call_state.value == "ended"
    assert session.escalation_reason == "customer_requested_human"
    assert "human follow-up" in session.summary.lower()

    log_path = tmp_path / f"{session.session_id}.json"
    assert log_path.exists()
    data = json.loads(log_path.read_text())
    assert data["outcome"] == "escalated"
    assert data["escalation_reason"] == "customer_requested_human"


@pytest.mark.asyncio
async def test_twilio_gather_resolves_without_live_call(tmp_path: Path):
    service = SessionService(GradioTransport(), SessionRegistry())
    service.persistence.log_dir = tmp_path

    session = await service.create_session(
        "John Smith hasn't paid his invoice of $450 from 15 April. Follow up and get a payment commitment.",
        "+61400000000",
    )
    session = await service.start_session(session)
    session.call_control_id = "call-control-123"
    session.twilio_gather_action_url_absolute = "https://example.com/webhooks/twilio/action"
    session.twilio_voice_url_absolute = "https://example.com/webhooks/twilio/voice"
    session.twilio_status_callback_url_absolute = "https://example.com/webhooks/twilio/status"
    session.voice_gather_started = True
    service.registry.save(session)

    await service.handle_twilio_gather(
        {"CallSid": "call-control-123", "SpeechResult": "Okay, what's this about?"}
    )
    await service.handle_twilio_gather(
        {"CallSid": "call-control-123", "SpeechResult": "Yes, I can pay tomorrow."}
    )
    _, twiml = await service.handle_twilio_gather(
        {"CallSid": "call-control-123", "SpeechResult": "Thanks, bye."}
    )
    updated = service.registry.get(session.session_id)
    assert updated is not None
    assert updated.outcome is not None
    assert updated.outcome.value == "resolved"
    assert updated.conversation_state.value == "closing"
    assert any("pay tomorrow" in entry.content.lower() for entry in updated.transcript)
    assert "<?xml" in twiml.lower() or "<response" in twiml.lower()


@pytest.mark.asyncio
async def test_mock_prompt_prepares_personalized_call_from_customer_directory(tmp_path: Path):
    workbook = tmp_path / "customers.xlsx"
    pd.DataFrame(
        [
            {"customer_id": 14, "customer_name": "Ava Thompson", "phone_number": "+61400000014"},
        ]
    ).to_excel(workbook, index=False)

    service = SessionService(GradioTransport(), SessionRegistry())
    prep = OutboundPrepService(CustomerDirectory(workbook), service)

    result = await prep.prepare_from_instruction("Customer ID 14, still owes $450, can you call them for me.")

    assert result.customer_record.customer_name == "Ava Thompson"
    assert result.parsed_intent.customer_id == 14
    assert result.parsed_intent.amount == "$450"
    assert "Ava Thompson" in result.personalized_message
    assert "$450" in result.personalized_message
