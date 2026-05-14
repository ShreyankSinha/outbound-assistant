from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from twilio.base.exceptions import TwilioRestException

from app.config import get_settings
from app.core.enums import CallState
from app.core.exceptions import ProviderError
from app.orchestration.call_lifecycle_manager import CallLifecycleManager
from app.schemas.session_state import SessionState
from app.transport.base_transport import BaseTransport
from app.transport.twilio.call_control import TwilioCallControl
from app.transport.twilio.outbound_call import TwilioOutboundCall

logger = logging.getLogger(__name__)


class TwilioTransport(BaseTransport):
    manages_live_call_lifecycle = True

    def __init__(self) -> None:
        self.lifecycle = CallLifecycleManager()
        self.outbound = TwilioOutboundCall()
        self.control = TwilioCallControl()

    async def start_session(self, session: SessionState) -> SessionState:
        session.telephony_provider = "twilio"
        self.lifecycle.transition(session, CallState.RINGING)
        if not session.call_target.startswith("+"):
            raise ProviderError("Twilio outbound calls require an E.164 destination number.")

        # Read simulation mode FRESH at call time — not from the session field
        # populated earlier by SessionService, which may have used a stale
        # settings cache.  This is the single authoritative check.
        current_settings = get_settings()
        sim_url: str | None = None
        if current_settings.twilio_simulation_mode:
            # Derive the ngrok root from the status callback URL already set
            # on the session (guaranteed populated before we get here).
            status_url = session.twilio_status_callback_url_absolute
            if status_url:
                base = status_url.rstrip("/").rsplit("/webhooks", 1)[0]
                sim_url = f"{base}/outbound-call"
                # Keep session field in sync so the sim routes can read it
                session.twilio_simulation_url_absolute = sim_url

        effective_to = current_settings.twilio_phone_number if sim_url else session.call_target
        print(
            f"[TwilioTransport.start_session] simulation_mode={current_settings.twilio_simulation_mode}  "
            f"sim_url={sim_url!r}  call_target={session.call_target!r}  effective_to={effective_to!r}"
        )

        try:
            result = self.outbound.create_outbound_call(
                to_number=session.call_target,
                session_id=session.session_id,
                voice_url_absolute=session.twilio_voice_url_absolute,
                status_callback_url=session.twilio_status_callback_url_absolute,
                async_amd_status_callback_url=session.twilio_status_callback_url_absolute,
                simulation_url_absolute=sim_url,
            )
        except TwilioRestException as exc:
            err = f"twilio_create_call_failed:{exc.status}:{getattr(exc, 'msg', str(exc))}"
            session.errors.append(err)
            logger.warning("twilio_create_call_failed", extra={"session_id": session.session_id, "error": err})
            self.lifecycle.transition(session, CallState.FAILED)
            raise ProviderError(f"Failed to create Twilio outbound call: {getattr(exc, 'msg', str(exc))}") from exc
        except Exception as exc:
            err = f"twilio_create_call_failed:{exc}"
            session.errors.append(err)
            logger.exception("twilio_create_call_failed", extra={"session_id": session.session_id})
            self.lifecycle.transition(session, CallState.FAILED)
            raise ProviderError(f"Failed to create Twilio outbound call: {exc}") from exc

        session.call_control_id = result.get("sid") or session.call_control_id
        return session

    async def end_session(self, session: SessionState, reason: str) -> SessionState:
        session.resolution_notes.append(f"call_end_reason:{reason}")
        if session.call_control_id and session.call_state not in {CallState.ENDED, CallState.FAILED}:
            try:
                self.control.hangup(session.call_control_id)
            except TwilioRestException as exc:
                session.errors.append(f"twilio_hangup_failed:{exc.status}:{exc.msg}")
                logger.warning("twilio_hangup_failed", extra={"session_id": session.session_id, "error_msg": str(exc)})
        if session.call_state != CallState.ENDED:
            self.lifecycle.transition(session, CallState.ENDED)
        return session

    async def receive_customer_input(self, session: SessionState) -> str:
        return session.customer_last_message

    async def send_agent_response(self, session: SessionState, response_text: str) -> None:
        session.agent_last_message = response_text

    async def handle_interrupt(self, session: SessionState) -> None:
        session.resolution_notes.append("customer_interrupted")

    async def stream_audio(self, session: SessionState, audio_stream: AsyncIterator[bytes]) -> None:
        async for _ in audio_stream:
            break
