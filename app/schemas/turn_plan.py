from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ActiveBlocker(BaseModel):
    type: str  # e.g. "payment_method_failure", "dispute", "wrong_person", "no_authority"
    details: str


class CustomerCommitment(BaseModel):
    status: str  # e.g. "none", "promised", "confirmed", "refused"
    timeline: str | None = None
    details: str | None = None


class TurnPlan(BaseModel):
    customer_intent: str
    conversation_phase: Literal["opening", "gathering", "resolving", "confirming", "closing"]
    active_blocker: ActiveBlocker | None = None
    customer_commitment: CustomerCommitment | None = None
    objective_met: bool = False
    should_close: bool = False
    should_escalate: bool = False
    escalation_reason: str | None = None
    next_action: Literal[
        "gather_information",
        "clarify_issue",
        "resolve_blocker",
        "confirm_commitment",
        "negotiate",
        "reassure",
        "escalate_to_human",
        "close_conversation",
        "leave_voicemail",
    ]
    reasoning: str
    agent_response: str
