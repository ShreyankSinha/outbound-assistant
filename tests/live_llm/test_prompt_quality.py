"""
Live LLM prompt quality tests.
These tests make REAL calls to the LLM backend (e.g. Groq).
They are intended to test prompt structure, reasoning and output shapes.
Do NOT run these in normal CI.
"""
import pytest

from app.core.enums import ConversationState
from app.llm.response_generator import ResponseGenerator
from app.schemas.parsed_intent import ParsedIntent
from app.schemas.transcript import TranscriptEntry

@pytest.fixture
def generator():
    return ResponseGenerator()

@pytest.fixture
def intent():
    return ParsedIntent(
        customer_id=99,
        issue_type="unpaid_invoice",
        customer_name="Live Test User",
        desired_resolution="payment commitment",
        raw_instruction="Call Live Test User",
        extracted_notes=[]
    )

@pytest.fixture
def transcript():
    return [
        TranscriptEntry(role="agent", content="Hello, I am calling about your unpaid invoice."),
    ]

@pytest.mark.asyncio
async def test_live_payment_commitment(generator, intent, transcript):
    decision = await generator.generate_decision(
        ConversationState.NEGOTIATING,
        intent,
        transcript,
        "I'll pay it on Friday."
    )
    
    assert decision.get("next_state") == "confirming"
    tools = decision.get("tools_to_call", [])
    assert any(t.get("name") == "log_payment_commitment" for t in tools)

@pytest.mark.asyncio
async def test_live_dispute(generator, intent, transcript):
    decision = await generator.generate_decision(
        ConversationState.NEGOTIATING,
        intent,
        transcript,
        "I already paid this last week, your system is wrong."
    )
    
    assert decision.get("next_state") == "escalating"
    tools = decision.get("tools_to_call", [])
    assert any(t.get("name") == "log_dispute" for t in tools)

@pytest.mark.asyncio
async def test_live_ambiguous_message(generator, intent, transcript):
    decision = await generator.generate_decision(
        ConversationState.NEGOTIATING,
        intent,
        transcript,
        "I'll sort it."
    )
    
    next_state = decision.get("next_state")
    assert next_state in ["negotiating", "confirming"]
    assert next_state != "closing"

@pytest.mark.asyncio
async def test_live_hostile_message(generator, intent, transcript):
    decision = await generator.generate_decision(
        ConversationState.NEGOTIATING,
        intent,
        transcript,
        "Stop calling me immediately, this is harassment."
    )
    
    assert decision.get("next_state") == "escalating"
    tools = decision.get("tools_to_call", [])
    assert any(t.get("name") == "escalate_to_human" for t in tools)
