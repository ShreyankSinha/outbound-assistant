import json
import pytest
from unittest.mock import AsyncMock, patch

from app.core.enums import ConversationState
from app.llm.response_generator import ResponseGenerator
from app.schemas.parsed_intent import ParsedIntent
from app.schemas.transcript import TranscriptEntry
from datetime import datetime, timezone

@pytest.fixture
def dummy_intent():
    return ParsedIntent(
        customer_id=1,
        issue_type="unpaid_invoice",
        customer_name="John Doe",
        desired_resolution="payment commitment",
        raw_instruction="Call John Doe",
        extracted_notes=[]
    )

@pytest.fixture
def dummy_transcript():
    return [
        TranscriptEntry(role="agent", content="Hello, John. I am calling about your unpaid invoice.", timestamp=datetime.now(timezone.utc).isoformat()),
    ]

@pytest.mark.parametrize("customer_message, mock_json, expected_state, expected_tool", [
    (
        "I'll pay next Tuesday", 
        {"next_state": "confirming", "agent_message": "Thank you.", "tools_to_call": [{"name": "log_payment_commitment", "args": {"date": "next Tuesday", "amount": "$100"}}]},
        "confirming", 
        "log_payment_commitment"
    ),
    (
        "I already paid this last week",
        {"next_state": "escalating", "agent_message": "I see. Let me check.", "tools_to_call": [{"name": "log_dispute", "args": {"reason": "paid last week"}}]},
        "escalating",
        "log_dispute"
    ),
    (
        "Maybe, I'll have to see",
        {"next_state": "negotiating", "agent_message": "Could you let me know today?", "tools_to_call": []},
        "negotiating",
        None
    ),
    (
        "I want to speak to a manager",
        {"next_state": "escalating", "agent_message": "Escalating now.", "tools_to_call": [{"name": "escalate_to_human", "args": {"reason": "requested manager"}}]},
        "escalating",
        "escalate_to_human"
    ),
    (
        "Can you call me back tomorrow?",
        {"next_state": "negotiating", "agent_message": "Sure.", "tools_to_call": [{"name": "schedule_callback", "args": {"date": "tomorrow"}}]},
        "negotiating",
        "schedule_callback"
    ),
    (
        "beep", # voicemail detected by system
        {"next_state": "voicemail", "agent_message": "Please call us back.", "tools_to_call": []},
        "voicemail",
        None
    )
])
@pytest.mark.asyncio
async def test_llm_scenarios(dummy_intent, dummy_transcript, customer_message, mock_json, expected_state, expected_tool):
    generator = ResponseGenerator()
    
    with patch("app.llm.groq_client.GroqLLMClient.complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = json.dumps(mock_json)
        decision = await generator.generate_decision(
            ConversationState.NEGOTIATING,
            dummy_intent,
            dummy_transcript,
            customer_message
        )
        
        assert decision["next_state"] == expected_state
        if expected_tool:
            tools = decision.get("tools_to_call", [])
            assert len(tools) > 0
            assert tools[0]["name"] == expected_tool

@pytest.mark.asyncio
async def test_malformed_json_fallback(dummy_intent, dummy_transcript):
    generator = ResponseGenerator()
    with patch("app.llm.groq_client.GroqLLMClient.complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = "{ not valid json"
        
        decision = await generator.generate_decision(
            ConversationState.NEGOTIATING,
            dummy_intent,
            dummy_transcript,
            "I don't know"
        )
        
        # It should retry once (2 calls total) and then fallback
        assert mock_complete.call_count == 2
        assert decision["next_state"] == ConversationState.NEGOTIATING.value
        assert "Sorry, give me one moment" in decision["agent_message"]
        assert "fallback: LLM response was malformed" in decision["reasoning"]

@pytest.mark.asyncio
async def test_invalid_next_state_fallback(dummy_intent, dummy_transcript):
    generator = ResponseGenerator()
    with patch("app.llm.groq_client.GroqLLMClient.complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = json.dumps({"next_state": "invalid_state", "agent_message": "Hello"})
        
        decision = await generator.generate_decision(
            ConversationState.NEGOTIATING,
            dummy_intent,
            dummy_transcript,
            "I don't know"
        )
        
        assert mock_complete.call_count == 2
        assert decision["next_state"] == ConversationState.NEGOTIATING.value
        assert "Sorry, give me one moment" in decision["agent_message"]

@pytest.mark.asyncio
async def test_retry_logic_succeeds_second_time(dummy_intent, dummy_transcript):
    generator = ResponseGenerator()
    with patch("app.llm.groq_client.GroqLLMClient.complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.side_effect = [
            "{ not valid json",
            json.dumps({"next_state": "closing", "agent_message": "Success!"})
        ]
        
        decision = await generator.generate_decision(
            ConversationState.NEGOTIATING,
            dummy_intent,
            dummy_transcript,
            "Okay bye"
        )
        
        assert mock_complete.call_count == 2
        assert decision["next_state"] == "closing"
        assert decision["agent_message"] == "Success!"
