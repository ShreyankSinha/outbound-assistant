from __future__ import annotations

from app.core.enums import CallState
from app.config import get_settings
from app.core.enums import ConversationState, SessionOutcome
from app.core.utils import new_session_id, utc_now_iso
from app.graph.builder import build_conversation_graph
from app.llm.instruction_parser import OperatorInstructionParser
from app.llm.response_generator import ResponseGenerator
from app.logging.session_persistence import SessionPersistence
from app.schemas.session_state import SessionState
from app.services.session_registry import SessionRegistry
from app.services.transcript_service import TranscriptService
from app.transport.base_transport import BaseTransport
from app.transport.telnyx_api import TelnyxCallControlClient
from app.transport.telnyx_transport import TelnyxTransport
from app.voice.session_controller import VoiceSessionController


class SessionService:
    def __init__(self, transport: BaseTransport, registry: SessionRegistry | None = None) -> None:
        self.settings = get_settings()
        self.parser = OperatorInstructionParser()
        self.responses = ResponseGenerator()
        self.persistence = SessionPersistence()
        self.transcripts = TranscriptService()
        self.voice = VoiceSessionController(transport)
        self.registry = registry or SessionRegistry()

    async def create_session(self, operator_instruction: str, call_target: str = "mock-customer") -> SessionState:
        parsed_intent = await self.parser.parse(operator_instruction)
        session = SessionState(
            session_id=new_session_id(),
            timestamp_start=utc_now_iso(),
            operator_instruction=operator_instruction,
            parsed_intent=parsed_intent,
            call_target=call_target,
        )
        return self.registry.save(session)

    async def start_session(self, session: SessionState) -> SessionState:
        if not session.agent_last_message:
            session.agent_last_message = await self.responses.generate(
                state=ConversationState.GREETING,
                intent=session.parsed_intent,
                transcript=session.transcript,
            )
        self.transcripts.add_entry(session, "agent", session.agent_last_message)
        session = await self.voice.start_outbound_call(session)
        if self.voice.transport.manages_live_call_lifecycle:
            session.conversation_state = ConversationState.UNDERSTANDING
            return self.registry.save(session)

        graph = build_conversation_graph(session.parsed_intent)
        graph_state = graph.invoke({"current_state": ConversationState.GREETING.value})
        session.conversation_state = ConversationState(graph_state["conversation_state"])
        await self.voice.play_response(session, session.agent_last_message)
        return self.registry.save(session)

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
        return self.registry.save(session)

    async def finalize_session(self, session: SessionState, end_call: bool = True) -> SessionState:
        if session.outcome is None:
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
        if end_call:
            await self.voice.end_call(session, session.outcome.value)
        self.persistence.persist(session)
        return self.registry.save(session)

    async def handle_telnyx_webhook(self, event: dict) -> SessionState | None:
        payload = event.get("data", {}).get("payload", {})
        event_type = event.get("data", {}).get("event_type", "")
        session = self.registry.get_by_call_control_id(payload.get("call_control_id"))
        session = session or self.registry.get_by_call_session_id(payload.get("call_session_id"))
        session = session or self.registry.get(self._decode_session_id(payload.get("client_state")))
        if not session:
            return None

        session.call_control_id = payload.get("call_control_id") or session.call_control_id
        session.call_session_id = payload.get("call_session_id") or session.call_session_id
        session.call_leg_id = payload.get("call_leg_id") or session.call_leg_id
        session.webhook_event_types.append(event_type)
        self.registry.bind_telnyx_call(session, session.call_control_id, session.call_session_id)

        if event_type == "call.initiated":
            session.call_state = CallState.RINGING
        elif event_type == "call.answered":
            session.call_state = CallState.ANSWERED
        elif event_type == "call.machine.detection.ended":
            result = payload.get("result", "")
            session.resolution_notes.append(f"amd_result:{result}")
            if result in {"human", "not_sure", "human_business", "human_residence"}:
                session.call_state = CallState.ACTIVE
                if isinstance(self.voice.transport, TelnyxTransport) and not session.telnyx_gather_started:
                    session = await self.voice.transport.start_ai_gather(session, session.agent_last_message)
            else:
                session.call_state = CallState.VOICEMAIL_DETECTED
                session.conversation_state = ConversationState.VOICEMAIL
        elif event_type == "call.machine.greeting.ended":
            if session.call_state == CallState.VOICEMAIL_DETECTED and isinstance(self.voice.transport, TelnyxTransport):
                voicemail_text = self._build_voicemail_message(session)
                self.transcripts.add_entry(session, "agent", voicemail_text)
                session = await self.voice.transport.leave_voicemail(session, voicemail_text)
        elif event_type == "call.ai_gather.ended":
            self._append_telnyx_message_history(session, payload.get("message_history", []))
            self._apply_telnyx_gather_result(session, payload.get("result", {}))
            await self.finalize_session(session, end_call=True)
        elif event_type == "call.hangup":
            session.call_state = CallState.ENDED
            if session.outcome is None:
                if session.conversation_state == ConversationState.VOICEMAIL or CallState.VOICEMAIL_DETECTED == session.call_state:
                    session.outcome = SessionOutcome.NO_ANSWER
                elif session.conversation_state == ConversationState.ESCALATING:
                    session.outcome = SessionOutcome.ESCALATED
                else:
                    session.outcome = SessionOutcome.FAILED
                await self.finalize_session(session, end_call=False)

        return self.registry.save(session)

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

    def _decode_session_id(self, client_state: str | None) -> str:
        return TelnyxCallControlClient.decode_client_state(client_state).get("session_id", "")

    def _append_telnyx_message_history(self, session: SessionState, history: list[dict]) -> None:
        for item in history:
            role = item.get("role", "")
            content = (item.get("content") or "").strip()
            if not content:
                continue
            normalized_role = "customer" if role == "user" else "agent"
            already_present = any(entry.role == normalized_role and entry.content == content for entry in session.transcript)
            if not already_present:
                self.transcripts.add_entry(session, normalized_role, content)

    def _apply_telnyx_gather_result(self, session: SessionState, result: dict) -> None:
        session.gather_result = result
        status = result.get("resolution_status", "unresolved")
        notes = result.get("notes", "")
        if notes:
            session.resolution_notes.append(notes)

        if status == "payment_committed":
            session.conversation_state = ConversationState.CLOSING
            session.outcome = SessionOutcome.RESOLVED
            if result.get("payment_date"):
                session.follow_up_actions = [f"Expect payment on {result['payment_date']}."]
        elif status == "callback_requested":
            session.conversation_state = ConversationState.CLOSING
            session.outcome = SessionOutcome.RESOLVED
            callback_time = result.get("callback_time") or "the requested time"
            session.follow_up_actions = [f"Place a callback at {callback_time}."]
        elif status in {"human_requested", "disputed", "unresolved"}:
            session.conversation_state = ConversationState.ESCALATING
            session.outcome = SessionOutcome.ESCALATED
            session.escalation_reason = status
            session.follow_up_actions = ["Human agent follow-up required."]
        else:
            session.conversation_state = ConversationState.ESCALATING
            session.outcome = SessionOutcome.FAILED
            session.escalation_reason = "telnyx_ai_gather_unrecognized_result"
            session.follow_up_actions = ["Review the call log and follow up manually."]

    def _build_voicemail_message(self, session: SessionState) -> str:
        issue = session.parsed_intent.issue_type.replace("_", " ")
        return (
            f"Hello, this is a follow-up call regarding your {issue}. "
            "Please call us back at your earliest convenience so we can help resolve it. Thank you."
        )
