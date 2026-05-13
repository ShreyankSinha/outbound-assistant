from __future__ import annotations

from app.config import get_settings
from app.core.enums import ConversationState, SessionOutcome
from app.core.utils import new_session_id, utc_now_iso
from app.graph.builder import build_conversation_graph
from app.llm.instruction_parser import OperatorInstructionParser
from app.llm.response_generator import ResponseGenerator
from app.logging.session_persistence import SessionPersistence
from app.schemas.session_state import SessionState
from app.services.transcript_service import TranscriptService
from app.transport.base_transport import BaseTransport
from app.voice.session_controller import VoiceSessionController


class SessionService:
    def __init__(self, transport: BaseTransport) -> None:
        self.settings = get_settings()
        self.parser = OperatorInstructionParser()
        self.responses = ResponseGenerator()
        self.persistence = SessionPersistence()
        self.transcripts = TranscriptService()
        self.voice = VoiceSessionController(transport)

    async def create_session(self, operator_instruction: str, call_target: str = "mock-customer") -> SessionState:
        parsed_intent = await self.parser.parse(operator_instruction)
        return SessionState(
            session_id=new_session_id(),
            timestamp_start=utc_now_iso(),
            operator_instruction=operator_instruction,
            parsed_intent=parsed_intent,
            call_target=call_target,
        )

    async def start_session(self, session: SessionState) -> SessionState:
        session = await self.voice.start_outbound_call(session)
        graph = build_conversation_graph(session.parsed_intent)
        response_state = ConversationState.GREETING
        graph_state = graph.invoke({"current_state": response_state.value})
        session.conversation_state = ConversationState(graph_state["conversation_state"])
        session.agent_last_message = await self.responses.generate(
            state=response_state,
            intent=session.parsed_intent,
            transcript=session.transcript,
        )
        self.transcripts.add_entry(session, "agent", session.agent_last_message)
        await self.voice.play_response(session, session.agent_last_message)
        return session

    async def handle_customer_turn(self, session: SessionState, customer_message: str) -> SessionState:
        session.turn_count += 1
        session.customer_last_message = customer_message
        self.transcripts.add_entry(session, "customer", customer_message)

        if self._needs_immediate_escalation(customer_message):
            session.conversation_state = ConversationState.ESCALATING
            session.escalation_reason = "customer_requested_human"
            session.agent_last_message = "I understand. I'll arrange a human follow-up from here."
        elif session.turn_count >= self.settings.max_turns_before_escalation:
            session.conversation_state = ConversationState.ESCALATING
            session.escalation_reason = "max_turns_before_escalation"
            session.agent_last_message = "I'll connect this to a human follow-up because we haven't resolved it yet."
        else:
            graph = build_conversation_graph(session.parsed_intent)
            response_state = session.conversation_state
            graph_state = graph.invoke(
                {
                    "current_state": response_state.value,
                    "latest_customer_message": customer_message,
                }
            )
            session.conversation_state = ConversationState(graph_state["conversation_state"])
            session.escalation_reason = graph_state.get("escalation_reason")
            resolution_note = graph_state.get("resolution_note")
            if resolution_note:
                session.resolution_notes.append(resolution_note)
            if session.conversation_state == ConversationState.CONFIRMING:
                response_state = ConversationState.CONFIRMING
                graph_state = graph.invoke(
                    {
                        "current_state": ConversationState.CONFIRMING.value,
                        "latest_customer_message": customer_message,
                        "resolution_note": resolution_note or customer_message,
                    }
                )
                session.conversation_state = ConversationState(graph_state["conversation_state"])
            if session.conversation_state in {ConversationState.CLOSING, ConversationState.ESCALATING, ConversationState.VOICEMAIL}:
                session.agent_last_message = graph_state.get("latest_agent_message", "")
            else:
                session.agent_last_message = await self.responses.generate(
                    state=response_state,
                    intent=session.parsed_intent,
                    transcript=session.transcript,
                    customer_message=customer_message,
                    escalation_reason=session.escalation_reason,
                )

        self.transcripts.add_entry(session, "agent", session.agent_last_message)
        await self.voice.play_response(session, session.agent_last_message)
        if session.conversation_state in {ConversationState.CLOSING, ConversationState.ESCALATING, ConversationState.VOICEMAIL}:
            await self.finalize_session(session)
        return session

    async def finalize_session(self, session: SessionState) -> SessionState:
        if session.conversation_state == ConversationState.CLOSING:
            session.outcome = SessionOutcome.RESOLVED
            session.follow_up_actions = []
        elif session.conversation_state == ConversationState.VOICEMAIL:
            session.outcome = SessionOutcome.NO_ANSWER
            session.follow_up_actions = ["Retry call or request human callback."]
        else:
            session.outcome = SessionOutcome.ESCALATED
            session.follow_up_actions = ["Human agent follow-up required."]

        session.summary = self._build_summary(session)
        session.timestamp_end = utc_now_iso()
        await self.voice.end_call(session, session.outcome.value)
        self.persistence.persist(session)
        return session

    def _build_summary(self, session: SessionState) -> str:
        if session.outcome == SessionOutcome.RESOLVED:
            note = session.resolution_notes[-1] if session.resolution_notes else "a resolution was reached"
            return f"The call reached a resolution. The customer indicated: {note}. The session closed without escalation."
        if session.outcome == SessionOutcome.NO_ANSWER:
            return "The outbound attempt did not reach a live conversation. A voicemail or no-answer path was recorded and follow-up is required."
        reason = session.escalation_reason or "the issue needs human review"
        return f"The call did not fully resolve. The conversation was escalated because {reason}. A human follow-up is required."

    def _needs_immediate_escalation(self, customer_message: str) -> bool:
        lowered = customer_message.lower()
        trigger_phrases = [
            "human",
            "person",
            "agent",
            "representative",
            "someone call me",
            "speak to someone",
        ]
        return any(phrase in lowered for phrase in trigger_phrases)
