from enum import Enum


class CallState(str, Enum):
    INITIATING = "initiating"
    RINGING = "ringing"
    ANSWERED = "answered"
    VOICEMAIL_DETECTED = "voicemail_detected"
    ACTIVE = "active"
    TRANSFERRING = "transferring"
    ENDED = "ended"
    FAILED = "failed"


class ConversationState(str, Enum):
    GREETING = "greeting"
    UNDERSTANDING = "understanding"
    NEGOTIATING = "negotiating"
    CONFIRMING = "confirming"
    CLOSING = "closing"
    ESCALATING = "escalating"
    VOICEMAIL = "voicemail"


class SessionOutcome(str, Enum):
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    NO_ANSWER = "no_answer"
    FAILED = "failed"
