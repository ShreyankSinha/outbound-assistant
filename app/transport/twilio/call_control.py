from __future__ import annotations

import logging
from typing import Any

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class TwilioCallControl:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def hangup(self, call_sid: str) -> None:
        if not call_sid:
            return
        if not self.settings.twilio_account_sid or not self.settings.twilio_auth_token:
            return
        client = Client(self.settings.twilio_account_sid, self.settings.twilio_auth_token)
        try:
            client.calls(call_sid).update(status="completed")
        except TwilioRestException as exc:
            logger.warning(
                "twilio_hangup_failed",
                extra={"call_sid": call_sid, "status": exc.status, "msg": str(exc)},
            )
            raise
