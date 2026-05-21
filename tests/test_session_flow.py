from pathlib import Path
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from app.schemas.turn_plan import TurnPlan, ActiveBlocker, CustomerCommitment
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
async def test_payment_blocker_transitions_to_negotiating_and_logs_blocker(tmp_path: Path):
    service = _build_service(tmp_path)
    session = await service.create_session("Collect $500 outstanding debt.")
    session = await service.start_session(session)
    
    plan = TurnPlan(
        customer_intent="Customer disputes the charge.",
        conversation_phase="resolving",
        next_action="resolve_blocker",
        reasoning="Customer is disputing the charge",
        agent_response="I understand you dispute this. Let's resolve it.",
        active_blocker=ActiveBlocker(type="dispute", details="Claims never received service.")
    )
    service.responses.plan_turn = AsyncMock(return_value=plan)
    
    session = await service.handle_customer_turn(session, "I never received the service!")
    
    assert session.active_blocker_type == "dispute"
    assert session.active_blocker_details == "Claims never received service."
    assert session.next_action == "resolve_blocker"
    assert session.conversation_state.value == "understanding"
    assert session.agent_last_message == plan.agent_response

@pytest.mark.asyncio
async def test_payment_commitment_updates_status_and_prepares_closing(tmp_path: Path):
    service = _build_service(tmp_path)
    session = await service.create_session("Collect $500 outstanding debt.")
    session = await service.start_session(session)
    
    plan = TurnPlan(
        customer_intent="Customer promises to pay tomorrow.",
        conversation_phase="closing",
        next_action="close_conversation",
        reasoning="Customer agreed to pay",
        should_close=True,
        agent_response="Thank you for confirming you'll pay tomorrow. Have a great day.",
        customer_commitment=CustomerCommitment(status="committed", timeline="tomorrow", details="Will pay online")
    )
    service.responses.plan_turn = AsyncMock(return_value=plan)
    
    session = await service.handle_customer_turn(session, "I'll pay it tomorrow online.")
    
    assert session.customer_commitment_status == "committed"
    assert session.customer_commitment_timeline == "tomorrow"
    assert session.conversation_state.value == "closing"
    assert session.outcome.value == "resolved"
    assert session.agent_last_message == plan.agent_response

@pytest.mark.asyncio
async def test_escalation_request_ends_call_with_escalated_outcome(tmp_path: Path):
    service = _build_service(tmp_path)
    session = await service.create_session("General inquiry.")
    session = await service.start_session(session)
    
    plan = TurnPlan(
        customer_intent="Customer demands to speak to human.",
        conversation_phase="closing",
        next_action="escalate_to_human",
        reasoning="Customer asked for a human",
        should_escalate=True,
        escalation_reason="Customer demanded manager.",
        agent_response="I'll transfer you to a human manager now."
    )
    service.responses.plan_turn = AsyncMock(return_value=plan)
    
    session = await service.handle_customer_turn(session, "Give me a manager!")
    
    assert session.conversation_state.value == "escalating"
    assert session.outcome.value == "escalated"
    assert session.escalation_reason == "Customer demanded manager."

@pytest.mark.asyncio
async def test_clean_close_ends_call_with_resolved_outcome(tmp_path: Path):
    service = _build_service(tmp_path)
    session = await service.create_session("Check if they are happy with service.")
    session = await service.start_session(session)
    
    plan = TurnPlan(
        customer_intent="Customer is happy and saying goodbye.",
        conversation_phase="closing",
        next_action="close_conversation",
        reasoning="Customer is happy",
        objective_met=True,
        agent_response="Great, thanks for your time. Bye!"
    )
    service.responses.plan_turn = AsyncMock(return_value=plan)
    
    session = await service.handle_customer_turn(session, "I'm happy, thanks bye.")
    
    assert session.conversation_state.value == "closing"
    assert session.outcome.value == "resolved"
    assert session.objective_met is True
    
@pytest.mark.asyncio
async def test_no_repetitive_questioning(tmp_path: Path):
    service = _build_service(tmp_path)
    session = await service.create_session("Find out their project plans.")
    session = await service.start_session(session)
    
    plan1 = TurnPlan(
        customer_intent="Provide info",
        conversation_phase="gathering",
        next_action="gather_information",
        reasoning="Gathering more info",
        agent_response="What else can you tell me?"
    )
    plan2 = TurnPlan(
        customer_intent="Provided all info",
        conversation_phase="closing",
        next_action="close_conversation",
        reasoning="All info gathered",
        objective_met=True,
        agent_response="Thanks for all the info. Bye."
    )
    service.responses.plan_turn = AsyncMock(side_effect=[plan1, plan2])
    
    session = await service.handle_customer_turn(session, "We are launching next week.")
    assert session.conversation_state.value == "understanding"
    
    session = await service.handle_customer_turn(session, "That's all the info.")
    assert session.conversation_state.value == "closing"
    assert session.objective_met is True

@pytest.mark.asyncio
async def test_general_objective_progresses_call(tmp_path: Path):
    service = _build_service(tmp_path)
    session = await service.create_session("General checkin.")
    session = await service.start_session(session)
    
    plan = TurnPlan(
        customer_intent="Customer is talking.",
        conversation_phase="gathering",
        next_action="gather_information",
        reasoning="Customer is talking",
        agent_response="Interesting, tell me more."
    )
    service.responses.plan_turn = AsyncMock(return_value=plan)
    
    session = await service.handle_customer_turn(session, "I am doing well.")
    
    assert session.conversation_state.value == "understanding"
    assert session.agent_last_message == "Interesting, tell me more."
    assert session.next_action == "gather_information"

@pytest.mark.asyncio
async def test_information_gathering_continues_call(tmp_path: Path):
    service = _build_service(tmp_path)
    session = await service.create_session("Gather details.")
    session = await service.start_session(session)
    
    plan = TurnPlan(
        customer_intent="Customer provided partial details.",
        conversation_phase="gathering",
        next_action="gather_information",
        reasoning="Need more details",
        agent_response="What about the timeline?"
    )
    service.responses.plan_turn = AsyncMock(return_value=plan)
    
    session = await service.handle_customer_turn(session, "Here is part of it.")
    
    assert session.conversation_state.value == "understanding"
    assert session.agent_last_message == "What about the timeline?"
