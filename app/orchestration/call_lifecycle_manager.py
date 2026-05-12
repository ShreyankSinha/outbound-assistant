from app.core.enums import CallState
from app.schemas.session_state import SessionState


class CallLifecycleManager:
    allowed_transitions = {
        CallState.INITIATING: {CallState.RINGING, CallState.FAILED},
        CallState.RINGING: {CallState.ANSWERED, CallState.VOICEMAIL_DETECTED, CallState.ENDED, CallState.FAILED},
        CallState.ANSWERED: {CallState.ACTIVE, CallState.ENDED, CallState.FAILED},
        CallState.VOICEMAIL_DETECTED: {CallState.ENDED},
        CallState.ACTIVE: {CallState.TRANSFERRING, CallState.ENDED, CallState.FAILED},
        CallState.TRANSFERRING: {CallState.ENDED, CallState.FAILED},
        CallState.ENDED: set(),
        CallState.FAILED: set(),
    }

    def transition(self, session: SessionState, new_state: CallState) -> SessionState:
        current = session.call_state
        if new_state not in self.allowed_transitions[current]:
            session.errors.append(f"invalid_call_transition:{current}->{new_state}")
            return session
        session.call_state = new_state
        return session
