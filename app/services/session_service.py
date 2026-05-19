from __future__ import annotations

from app.config import get_settings
from app.core.enums import CallState, ConversationState, SessionOutcome
from app.core.exceptions import ProviderError
from app.core.utils import new_session_id, utc_now_iso
from app.graph.nodes import agent_node
from app.llm.instruction_parser import OperatorInstructionParser
from app.llm.response_generator import ResponseGenerator
from app.logging.session_persistence import SessionPersistence
from app.orchestration.call_lifecycle_manager import CallLifecycleManager
from app.schemas.session_state import SessionState
from app.services.session_registry import SessionRegistry
from app.services.transcript_service import TranscriptService
from app.transport.base_transport import BaseTransport
from app.transport.twilio.twiml_builder import (
    build_amd_wait_twiml,
    build_closing_twiml,
    build_continue_gather_twiml,
    build_opening_gather_twiml,
    build_voicemail_twiml,
)
from app.transport.twilio.urls import twilio_webhook_urls_from_status_callback
from app.transport.twilio.webhook_handler import (
    is_human_amd,
    is_voicemail_amd,
    map_twilio_call_status_to_call_state,
)
from app.transport.twilio_transport import TwilioTransport
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
        self.call_lifecycle = CallLifecycleManager()

    def _configure_twilio_webhook_urls(self, session: SessionState) -> None:
        if not self.settings.twilio_status_callback_url:
            raise ValueError("TWILIO_STATUS_CALLBACK_URL is required for Twilio transport.")
        voice, status, action = twilio_webhook_urls_from_status_callback(self.settings.twilio_status_callback_url)
        session.twilio_voice_url_absolute = voice
        session.twilio_status_callback_url_absolute = status
        session.twilio_gather_action_url_absolute = action

    async def create_session(self, operator_instruction: str, call_target: str = "mock-customer") -> SessionState:
        parsed_intent = await self.parser.parse(operator_instruction)
        session = SessionState(
            session_id=new_session_id(),
            timestamp_start=utc_now_iso(),
            operator_instruction=operator_instruction,
            parsed_intent=parsed_intent,
            call_target=call_target,
        )
        session.topic_two_complete = None if parsed_intent.single_topic else False
        if parsed_intent.phone_number and call_target == "mock-customer":
            session.call_target = parsed_intent.phone_number
        return self.registry.save(session)

    async def start_session(self, session: SessionState) -> SessionState:
        if not session.agent_last_message:
            decision = await agent_node(
                {
                    "transcript": session.transcript,
                    "current_topic": session.current_topic,
                    "topic_one_complete": session.topic_one_complete,
                    "topic_two_complete": session.topic_two_complete,
                },
                session.parsed_intent,
                self.responses,
            )
            session.agent_last_message = decision["agent_message"]
            session.conversation_state = ConversationState(decision["conversation_state"])
        self.transcripts.add_entry(session, "agent", session.agent_last_message)
        if isinstance(self.voice.transport, TwilioTransport):
            try:
                self._configure_twilio_webhook_urls(session)
            except ValueError as exc:
                raise ProviderError(str(exc)) from exc
        session = await self.voice.start_outbound_call(session)
        if self.voice.transport.manages_live_call_lifecycle:
            session.conversation_state = ConversationState.UNDERSTANDING
            return self.registry.save(session)
        await self.voice.play_response(session, session.agent_last_message)
        return self.registry.save(session)

    async def apply_customer_speech(self, session: SessionState, customer_message: str) -> SessionState:
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
            previous_topic = session.current_topic
            graph_state = await agent_node(
                {
                    "current_state": session.conversation_state.value,
                    "latest_customer_message": customer_message,
                    "current_topic": session.current_topic,
                    "topic_one_complete": session.topic_one_complete,
                    "topic_two_complete": session.topic_two_complete,
                    "transcript": session.transcript,
                    "turn_count": session.turn_count,
                },
                session.parsed_intent,
                self.responses,
            )
            session.conversation_state = ConversationState(graph_state["conversation_state"])
            session.escalation_reason = graph_state.get("escalation_reason")
            session.current_topic = graph_state.get("current_topic", session.current_topic)
            session.topic_one_complete = graph_state.get("topic_one_complete", session.topic_one_complete)
            session.topic_two_complete = graph_state.get("topic_two_complete", session.topic_two_complete)
            self._append_resolution_note(session, graph_state.get("resolution_note"))
            if previous_topic == 1 and session.current_topic == 2:
                self._append_resolution_note(session, f"topic_transition_turn:{session.turn_count}")
            session.agent_last_message = graph_state.get("agent_message") or graph_state.get("latest_agent_message", "")

        self.transcripts.add_entry(session, "agent", session.agent_last_message)
        return session

    async def handle_customer_turn(self, session: SessionState, customer_message: str) -> SessionState:
        session = await self.apply_customer_speech(session, customer_message)
        await self.voice.play_response(session, session.agent_last_message)
        if session.conversation_state in {ConversationState.CLOSING, ConversationState.ESCALATING, ConversationState.VOICEMAIL}:
            await self.finalize_session(session)
        return self.registry.save(session)

    async def finalize_session(self, session: SessionState, end_call: bool = True) -> SessionState:
        if session.timestamp_end:
            return self.registry.save(session)
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

        session.summary = await self.responses.generate_summary(session.parsed_intent, session.transcript)
        session.timestamp_end = utc_now_iso()
        if end_call:
            await self.voice.end_call(session, session.outcome.value)
        self.persistence.persist(session)
        return self.registry.save(session)

    def _gather_action_url(self, session: SessionState) -> str:
        base = session.twilio_gather_action_url_absolute
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}session_id={session.session_id}"

    def _voice_url(self, session: SessionState) -> str:
        base = session.twilio_voice_url_absolute
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}session_id={session.session_id}"

    def build_twilio_voice_twiml(self, session: SessionState) -> str:
        if session.conversation_state == ConversationState.VOICEMAIL or session.call_state == CallState.VOICEMAIL_DETECTED:
            if not session.voicemail_message_played:
                text = self._build_voicemail_message(session)
                self.transcripts.add_entry(session, "agent", text)
                session.voicemail_message_played = True
                return build_voicemail_twiml(message=text)
            return build_closing_twiml(message="Goodbye.")

        if session.twilio_amd_answered_by is None:
            if session.twilio_voice_redirects >= 30:
                session.twilio_amd_answered_by = "human"
                session.resolution_notes.append("amd_result:timeout_assumed_human")
            else:
                session.twilio_voice_redirects += 1
                return build_amd_wait_twiml(next_url_absolute=self._voice_url(session))

        answered = (session.twilio_amd_answered_by or "").lower()
        if is_voicemail_amd(session.twilio_amd_answered_by):
            self.call_lifecycle.transition(session, CallState.VOICEMAIL_DETECTED)
            session.conversation_state = ConversationState.VOICEMAIL
            if not session.voicemail_message_played:
                text = self._build_voicemail_message(session)
                self.transcripts.add_entry(session, "agent", text)
                session.voicemail_message_played = True
                return build_voicemail_twiml(message=text)
            return build_closing_twiml(message="Goodbye.")

        if is_human_amd(session.twilio_amd_answered_by) or answered == "unknown":
            if not session.voice_gather_started:
                session.voice_gather_started = True
                return build_opening_gather_twiml(
                    opening_text=session.agent_last_message,
                    gather_action_url_absolute=self._gather_action_url(session),
                )
            return build_continue_gather_twiml(
                agent_text=session.agent_last_message,
                gather_action_url_absolute=self._gather_action_url(session),
            )

        return build_closing_twiml(message="Thank you, goodbye.")

    async def handle_twilio_gather(self, form: dict[str, str]) -> tuple[SessionState | None, str]:
        call_sid = form.get("CallSid") or ""
        session = self.registry.get_by_call_control_id(call_sid) if call_sid else None
        sid = form.get("session_id") or form.get("SessionId")
        session = session or (self.registry.get(sid) if sid else None)
        if not session:
            return None, build_closing_twiml(message="Goodbye.")

        speech = (form.get("SpeechResult") or form.get("StableSpeechResult") or "").strip()
        if not speech:
            twiml = build_continue_gather_twiml(
                agent_text="Sorry, I did not catch that. Could you please repeat?",
                gather_action_url_absolute=self._gather_action_url(session),
            )
            return self.registry.save(session), twiml

        session = await self.apply_customer_speech(session, speech)
        if session.conversation_state in {ConversationState.CLOSING, ConversationState.ESCALATING, ConversationState.VOICEMAIL}:
            twiml = build_closing_twiml(message=session.agent_last_message)
            await self.finalize_session(session, end_call=False)
            return self.registry.save(session), twiml

        twiml = build_continue_gather_twiml(
            agent_text=session.agent_last_message,
            gather_action_url_absolute=self._gather_action_url(session),
        )
        return self.registry.save(session), twiml

    async def handle_twilio_status(self, form: dict[str, str]) -> SessionState | None:
        call_sid = form.get("CallSid") or ""
        call_status = (form.get("CallStatus") or "").strip()
        answered_by = form.get("AnsweredBy")
        session = self.registry.get_by_call_control_id(call_sid) if call_sid else None
        if not session:
            return None

        session.call_control_id = call_sid or session.call_control_id
        self.registry.bind_call_leg(session, session.call_control_id, session.call_session_id)

        if answered_by:
            session.twilio_amd_answered_by = answered_by
            session.resolution_notes.append(f"amd_result:{answered_by}")
            if is_voicemail_amd(answered_by):
                self.call_lifecycle.transition(session, CallState.VOICEMAIL_DETECTED)
                session.conversation_state = ConversationState.VOICEMAIL
            elif is_human_amd(answered_by):
                if session.call_state == CallState.RINGING:
                    self.call_lifecycle.transition(session, CallState.ANSWERED)
                if session.call_state == CallState.ANSWERED:
                    self.call_lifecycle.transition(session, CallState.ACTIVE)

        event_key = f"status:{call_status}" + (f":amd:{answered_by}" if answered_by else "")
        session.webhook_event_types.append(event_key)

        if call_status:
            mapped = map_twilio_call_status_to_call_state(call_status)
            cs = call_status.lower()
            if mapped == CallState.RINGING and session.call_state == CallState.INITIATING:
                self.call_lifecycle.transition(session, CallState.RINGING)
            elif mapped == CallState.RINGING and session.call_state not in {
                CallState.RINGING,
                CallState.VOICEMAIL_DETECTED,
                CallState.ENDED,
                CallState.FAILED,
            }:
                self.call_lifecycle.transition(session, CallState.RINGING)
            elif mapped == CallState.ANSWERED:
                if session.call_state == CallState.INITIATING:
                    self.call_lifecycle.transition(session, CallState.RINGING)
                if session.call_state == CallState.RINGING:
                    self.call_lifecycle.transition(session, CallState.ANSWERED)
            elif mapped == CallState.FAILED:
                self.call_lifecycle.transition(session, CallState.FAILED)
                if session.outcome is None:
                    session.outcome = SessionOutcome.FAILED
                await self.finalize_session(session, end_call=False)
            elif mapped == CallState.ENDED:
                if session.outcome is None:
                    if cs == "no-answer":
                        session.outcome = SessionOutcome.NO_ANSWER
                    elif cs == "busy":
                        session.outcome = SessionOutcome.FAILED
                    elif session.conversation_state == ConversationState.VOICEMAIL or session.call_state == CallState.VOICEMAIL_DETECTED:
                        session.outcome = SessionOutcome.NO_ANSWER
                    elif session.conversation_state == ConversationState.ESCALATING:
                        session.outcome = SessionOutcome.ESCALATED
                    elif session.conversation_state == ConversationState.CLOSING:
                        session.outcome = SessionOutcome.RESOLVED
                    elif cs == "failed":
                        session.outcome = SessionOutcome.FAILED
                    else:
                        session.outcome = SessionOutcome.FAILED
                self.call_lifecycle.transition(session, CallState.ENDED)
                await self.finalize_session(session, end_call=False)

        return self.registry.save(session)

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

    def _build_voicemail_message(self, session: SessionState) -> str:
        issue = session.parsed_intent.issue_type.replace("_", " ")
        return (
            f"Hello, this is a follow-up call regarding your {issue}. "
            "Please call us back at your earliest convenience so we can help resolve it. Thank you."
        )

    @staticmethod
    def _append_resolution_note(session: SessionState, note: str | None) -> None:
        if note and note not in session.resolution_notes:
            session.resolution_notes.append(note)
