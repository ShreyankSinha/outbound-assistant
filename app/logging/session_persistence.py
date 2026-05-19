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
        return path

    def _render_log(self, session: SessionState, timestamp: datetime) -> str:
        topic_one_summary, topic_two_summary = self._topic_summaries(session)
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
            "SUMMARY",
            "-------------------------------------",
            f"Topic 1 - {session.parsed_intent.topic_one}:",
            f"  {topic_one_summary}",
        ]
        if not session.parsed_intent.single_topic and session.parsed_intent.topic_two:
            lines.extend(
                [
                    "",
                    f"Topic 2 - {session.parsed_intent.topic_two}:",
                    f"  {topic_two_summary}",
                ]
            )
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

    def _topic_summaries(self, session: SessionState) -> tuple[str, str]:
        customer_messages = [entry.content.strip() for entry in session.transcript if entry.role.lower() == "customer"]
        transition_index = self._topic_two_transition_index(session)
        topic_one_messages = customer_messages[:transition_index] if transition_index is not None else customer_messages
        topic_two_messages = customer_messages[transition_index:] if transition_index is not None else []
        topic_one_summary = self._format_topic_summary(session.parsed_intent.topic_one, topic_one_messages)
        topic_two_summary = self._format_topic_summary(session.parsed_intent.topic_two or "", topic_two_messages)
        return topic_one_summary, topic_two_summary

    @staticmethod
    def _format_topic_summary(topic_label: str, messages: list[str]) -> str:
        if not topic_label:
            return "No additional topic summary was needed."
        if not messages:
            return (
                f"The call touched on {topic_label}, but the customer did not give a detailed answer before the topic moved on."
            )
        first_message = messages[0].rstrip(".")
        last_message = messages[-1].rstrip(".")
        if first_message == last_message:
            return (
                f"The discussion covered {topic_label}. The customer explained that {first_message}. "
                "Alex captured that response for follow-up."
            )
        return (
            f"The discussion covered {topic_label}. The customer first shared that {first_message}. "
            f"By the end of the topic, they added that {last_message}."
        )

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
    def _topic_two_transition_index(session: SessionState) -> int | None:
        for note in session.resolution_notes:
            if note.startswith("topic_transition_turn:"):
                try:
                    return int(note.split(":", maxsplit=1)[1]) - 1
                except ValueError:
                    return None
        return None

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
