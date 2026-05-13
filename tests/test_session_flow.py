import json
from pathlib import Path

import pytest

from app.services.session_service import SessionService
from app.transport.gradio_transport import GradioTransport


@pytest.mark.asyncio
async def test_happy_path_resolves_and_persists_log(tmp_path: Path):
    service = SessionService(GradioTransport())
    service.persistence.log_dir = tmp_path

    session = await service.create_session(
        "John Smith hasn't paid his invoice of $450 from 15 April. Follow up and get a payment commitment."
    )
    session = await service.start_session(session)
    session = await service.handle_customer_turn(session, "Okay, what's this about?")
    session = await service.handle_customer_turn(session, "Yes, I can pay tomorrow")

    assert session.outcome is not None
    assert session.outcome.value == "resolved"
    assert session.call_state.value == "ended"
    assert session.summary
    assert "Yes, I can pay tomorrow" in session.summary

    log_path = tmp_path / f"{session.session_id}.json"
    assert log_path.exists()
    data = json.loads(log_path.read_text())
    assert data["outcome"] == "resolved"
    assert len(data["transcript"]) >= 5


@pytest.mark.asyncio
async def test_customer_human_request_escalates_and_persists_log(tmp_path: Path):
    service = SessionService(GradioTransport())
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
