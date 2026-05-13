from __future__ import annotations

from app.core.enums import CallState


def map_twilio_call_status_to_call_state(call_status: str) -> CallState | None:
    s = (call_status or "").strip().lower()
    if s in {"queued", "initiated"}:
        return CallState.RINGING
    if s == "ringing":
        return CallState.RINGING
    if s in {"in-progress", "answered"}:
        return CallState.ANSWERED
    if s in {"completed", "canceled", "cancelled"}:
        return CallState.ENDED
    if s == "busy":
        return CallState.ENDED
    if s == "failed":
        return CallState.FAILED
    if s == "no-answer":
        return CallState.ENDED
    return None


def is_voicemail_amd(answered_by: str | None) -> bool:
    if not answered_by:
        return False
    a = answered_by.strip().lower()
    return a in {"machine_start", "machine_end_beep", "machine_end_silence", "machine_end_other", "fax"}


def is_human_amd(answered_by: str | None) -> bool:
    if not answered_by:
        return False
    return answered_by.strip().lower() == "human"
