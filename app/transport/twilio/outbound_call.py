from __future__ import annotations

import logging
from typing import Any

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class TwilioOutboundCall:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def create_outbound_call(
        self,
        *,
        to_number: str,
        session_id: str,
        voice_url_absolute: str,
        status_callback_url: str,
        async_amd_status_callback_url: str,
    ) -> dict[str, Any]:
        if not self.settings.twilio_account_sid or not self.settings.twilio_auth_token:
            raise ValueError("Twilio account credentials are not configured.")
        if not self.settings.twilio_phone_number:
            raise ValueError("TWILIO_PHONE_NUMBER is not configured.")

        client = Client(self.settings.twilio_account_sid, self.settings.twilio_auth_token)
        sep = "&" if "?" in voice_url_absolute else "?"
        url = f"{voice_url_absolute}{sep}session_id={session_id}"

        try:
            call = client.calls.create(
                to=to_number,
                from_=self.settings.twilio_phone_number,
                url=url,
                method="POST",
                machine_detection="Enable",
                async_amd="true",
                async_amd_status_callback=async_amd_status_callback_url,
                async_amd_status_callback_method="POST",
                status_callback=status_callback_url,
                status_callback_method="POST",
                status_callback_event=["initiated", "ringing", "answered", "completed"],
            )
        except TwilioRestException as exc:
            logger.warning(
                "twilio_calls_create_failed",
                extra={"status": exc.status, "error_msg": str(exc), "session_id": session_id},
            )
            raise
        return {"sid": call.sid, "status": call.status}
