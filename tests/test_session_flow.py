from pathlib import Path
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from app.services.customer_directory import CustomerDirectory
from app.services.outbound_prep_service import OutboundPrepService
from app.services.session_registry import SessionRegistry
from app.services.session_service import SessionService
from app.transport.gradio_transport import GradioTransport


def _build_service(tmp_path: Path) -> SessionService:
    service = SessionService(GradioTransport(), SessionRegistry())
    service.persistence.log_dir = tmp_path
    service.parser.llm_client.client = None
    service.responses.llm_client.client = None
    return service


@pytest.mark.asyncio
async def test_single_topic_flow_resolves_and_persists_log(tmp_path: Path):
    service = _build_service(tmp_path)

    session = await service.create_session(
        "Customer ID 1. Find out what the customer's plans are for the project they are working on."
    )
    session = await service.start_session(session)
    session = await service.handle_customer_turn(session, "We're planning to roll it out next quarter.")

    assert session.outcome is not None
    assert session.outcome.value == "resolved"
    assert session.call_state.value == "ended"
    assert session.current_topic == 1
    assert session.topic_one_complete is True
    assert session.topic_two_complete is None

    logs = list(tmp_path.glob("*_customer_1.txt"))
    assert len(logs) == 1
    content = logs[0].read_text(encoding="utf-8")
    assert "iSoft Call Summary" in content
    assert "Topic 1 - Find out what the customer's plans are for the project they are working on:" in content
    assert "Topic 2 -" not in content
    assert "[AGENT]" in content
    assert "[CUSTOMER]" in content


@pytest.mark.asyncio
async def test_customer_human_request_escalates_and_persists_log(tmp_path: Path):
    service = _build_service(tmp_path)

    session = await service.create_session(
        "Customer ID 1. Find out what the customer's plans are for the project they are working on."
    )
    session = await service.start_session(session)
    session = await service.handle_customer_turn(session, "I want to speak to a human")

    assert session.outcome is not None
    assert session.outcome.value == "escalated"
    assert session.call_state.value == "ended"
    assert session.escalation_reason == "customer_requested_human"

    logs = list(tmp_path.glob("*_customer_1.txt"))
    assert len(logs) == 1
    content = logs[0].read_text(encoding="utf-8")
    assert "Overall Notes:" in content
    assert "Escalation reason: customer_requested_human" in content


@pytest.mark.asyncio
async def test_two_topic_flow_and_log_creation(tmp_path: Path):
    service = _build_service(tmp_path)
    service.responses.judge_topic_transition = AsyncMock(
        side_effect=[
            {"topic_one_complete": False, "reasoning": "Need a bit more detail on topic one."},
            {"topic_one_complete": True, "reasoning": "Topic one is complete, so we can move to topic two."},
        ]
    )

    session = await service.create_session(
        "Customer ID 1. Find out what the customer's plans are for the project they are working on and get a sense of the timeline."
    )
    session = await service.start_session(session)

    session = await service.handle_customer_turn(session, "We're still shaping the project scope.")
    assert session.outcome is None
    assert session.current_topic == 1
    assert session.topic_one_complete is False
    assert session.topic_two_complete is False

    session = await service.handle_customer_turn(session, "The team wants to start implementation once the plan is agreed.")
    assert session.outcome is None
    assert session.current_topic == 2
    assert session.topic_one_complete is True
    assert session.topic_two_complete is False
    assert "timeline" in session.agent_last_message.lower()

    session = await service.handle_customer_turn(session, "If everything lines up, we'd aim for late August.")
    assert session.outcome is not None
    assert session.outcome.value == "resolved"
    assert session.current_topic == 2
    assert session.topic_one_complete is True
    assert session.topic_two_complete is True

    logs = list(tmp_path.glob("*_customer_1.txt"))
    assert len(logs) == 1
    content = logs[0].read_text(encoding="utf-8")
    assert "Topic 1 - Find out what the customer's plans are for the project they are working on:" in content
    assert "Topic 2 - the timeline:" in content
    assert "TRANSCRIPT" in content
    assert "[AGENT]" in content
    assert "[CUSTOMER]" in content


@pytest.mark.asyncio
async def test_mock_prompt_prepares_personalized_call_from_customer_directory(tmp_path: Path):
    workbook = tmp_path / "customers.xlsx"
    pd.DataFrame(
        [
            {"customer_id": 14, "customer_name": "Ava Thompson", "phone_number": "+61400000014"},
        ]
    ).to_excel(workbook, index=False)

    service = _build_service(tmp_path)
    prep = OutboundPrepService(CustomerDirectory(workbook), service, parser=service.parser)

    result = await prep.prepare_from_instruction(
        "Customer ID 14. Find out what the customer's plans are for the project they are working on and get a sense of the timeline."
    )

    assert result.customer_record.customer_name == "Ava Thompson"
    assert result.parsed_intent.customer_id == 14
    assert result.parsed_intent.phone_number == "+61400000014"
    assert result.parsed_intent.topic_one == "Find out what the customer's plans are for the project they are working on"
    assert result.parsed_intent.topic_two == "the timeline"
    assert "Ava Thompson" in result.personalized_message


@pytest.mark.asyncio
async def test_topic_follow_up_uses_full_up_to_date_transcript(tmp_path: Path):
    service = _build_service(tmp_path)
    session = await service.create_session(
        "Customer ID 1. Find out what the customer's plans are for the project they are working on."
    )
    session = await service.start_session(session)

    captured: dict[str, str] = {}

    async def fake_complete(system_prompt: str, user_prompt: str, prefer_fallback: bool = False) -> str:
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        return "What are the next steps after the August pilot?"

    service.responses.llm_client.client = object()
    service.responses.llm_client.complete = AsyncMock(side_effect=fake_complete)
    service.responses.judge_topic_transition = AsyncMock(
        return_value={"topic_one_complete": False, "reasoning": "Still gathering details on topic one."}
    )

    session = await service.handle_customer_turn(session, "We're planning an August pilot and then a wider rollout.")

    assert session.agent_last_message == "What are the next steps after the August pilot?"
    assert "Latest customer message: We're planning an August pilot and then a wider rollout." in captured["user_prompt"]
    assert "[AGENT]" in captured["user_prompt"]
    assert "[CUSTOMER] We're planning an August pilot and then a wider rollout." in captured["user_prompt"]


@pytest.mark.asyncio
async def test_closing_message_strips_meta_text_from_llm_output(tmp_path: Path):
    service = _build_service(tmp_path)
    session = await service.create_session(
        "Customer ID 1. Find out what the customer's plans are for the project they are working on."
    )
    session = await service.start_session(session)
    session = await service.apply_customer_speech(session, "We're planning to roll it out next quarter.")

    service.responses.llm_client.client = object()
    service.responses.llm_client.complete = AsyncMock(
        return_value="Here's a natural closing for the call:\nThanks for your time today. Goodbye."
    )

    closing = await service.responses.generate_closing_message(session.parsed_intent, session.transcript)

    assert closing == "Thanks for your time today. Goodbye."
