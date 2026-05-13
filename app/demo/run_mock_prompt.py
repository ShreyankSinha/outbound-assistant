from __future__ import annotations

import asyncio
import json

from app.config import get_settings
from app.services.customer_directory import CustomerDirectory
from app.services.outbound_prep_service import OutboundPrepService
from app.services.session_registry import SessionRegistry
from app.services.session_service import SessionService
from app.transport.gradio_transport import GradioTransport
from app.transport.twilio_transport import TwilioTransport


async def main() -> None:
    instruction = "Customer ID 14, still owes $450, can you call them for me."
    settings = get_settings()
    transport = TwilioTransport() if settings.enable_twilio_transport else GradioTransport()
    service = SessionService(transport, SessionRegistry())
    prep = OutboundPrepService(CustomerDirectory(), service)
    result = await prep.attempt_call_from_instruction(instruction)
    print(
        json.dumps(
            {
                "operator_instruction": result.operator_instruction,
                "parsed_intent": result.parsed_intent.model_dump(),
                "customer_record": result.customer_record.model_dump(),
                "personalized_message": result.personalized_message,
                "telephony_attempted": result.telephony_attempted,
                "telephony_error": result.telephony_error,
                "session": result.session.model_dump() if result.session else None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
