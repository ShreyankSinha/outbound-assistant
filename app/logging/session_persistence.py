from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.schemas.session_state import SessionState


class SessionPersistence:
    def __init__(self, log_dir: str | None = None) -> None:
        settings = get_settings()
        self.log_dir = Path(log_dir or settings.log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def persist(self, session: SessionState) -> Path:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = self._parse_timestamp(session.timestamp_end or session.timestamp_start)
        customer_id = session.parsed_intent.customer_id if session.parsed_intent.customer_id is not None else "unknown"
        filename = f"{timestamp:%Y%m%d_%H%M%S}_customer_{customer_id}.txt"
        path = self.log_dir / filename
        path.write_text(self._render_log(session, timestamp), encoding="utf-8")
        
        json_path = path.with_suffix(".json")
        json_path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        
        return path

    def _render_log(self, session: SessionState, timestamp: datetime) -> str:
        overall_notes = self._overall_notes(session)
        lines = [
            "=====================================",
            "         iSoft Call Summary",
            "=====================================",
            f"Date:           {timestamp:%d %b %Y}",
            f"Time:           {timestamp:%H:%M:%S}",
            f"Customer ID:    {session.parsed_intent.customer_id if session.parsed_intent.customer_id is not None else 'Unknown'}",
            f"Duration:       ~{max(session.turn_count, 1)} turns",
            "",
            "-------------------------------------",
            "DECISIONS",
            "-------------------------------------",
        ]
        
        if session.turn_plans:
            for i, plan in enumerate(session.turn_plans, 1):
                action = plan.get("next_action", "unknown")
                reasoning = plan.get("reasoning", "No reasoning provided.")
                lines.append(f"Turn {i} — next_action: {action} | reasoning: {reasoning}")
        else:
            lines.append("No turn plans recorded.")

        lines.extend(
            [
                "",
                "Overall Notes:",
                f"  {overall_notes}",
                "",
                "-------------------------------------",
                "TRANSCRIPT",
                "-------------------------------------",
            ]
        )
        lines.extend(self._transcript_lines(session))
        lines.extend(
            [
                "",
                "=====================================",
                "         End of Call Log",
                "=====================================",
            ]
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _overall_notes(session: SessionState) -> str:
        notes = []
        for note in session.resolution_notes:
            if note.startswith("topic_transition_turn:") or note.startswith("call_end_reason:"):
                continue
            notes.append(note)
        if session.escalation_reason:
            notes.append(f"Escalation reason: {session.escalation_reason}")
        return " ".join(notes).strip() or "None."

    @staticmethod
    def _transcript_lines(session: SessionState) -> list[str]:
        rendered = []
        for entry in session.transcript:
            label = "[AGENT]" if entry.role.lower() == "agent" else "[CUSTOMER]"
            rendered.append(f"{label:<11} {entry.content}")
        return rendered



    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
