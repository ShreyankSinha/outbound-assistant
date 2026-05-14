from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.api.routes_twilio_webhooks import create_twilio_router
from app.api.routes_twilio_ws import create_twilio_ws_router
from app.config import get_settings
from app.core.exceptions import ProviderError
from app.services.customer_directory import CustomerDirectory
from app.services.outbound_prep_service import OutboundPrepService
from app.services.session_service import SessionService
from app.services.session_registry import SessionRegistry
from app.transport.gradio_transport import GradioTransport
from app.transport.twilio_transport import TwilioTransport

app = FastAPI(title="Outbound Assistant")
settings = get_settings()
registry = SessionRegistry()
transport = TwilioTransport() if settings.enable_twilio_transport else GradioTransport()
session_service = SessionService(transport, registry)
customer_directory = CustomerDirectory()
prep_service = OutboundPrepService(customer_directory, session_service)

app.include_router(create_twilio_router(session_service))
app.include_router(create_twilio_ws_router())


class StartSessionRequest(BaseModel):
    # Accept either 'instruction' (test script) or 'operator_instruction' (legacy)
    operator_instruction: str = Field(default="", alias="operator_instruction")
    instruction: str = Field(default="", alias="instruction")
    call_target: str = "mock-customer"

    model_config = {"populate_by_name": True}

    def resolved_instruction(self) -> str:
        return self.instruction or self.operator_instruction


class CustomerTurnRequest(BaseModel):
    customer_message: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sessions")
async def create_session(request: StartSessionRequest):
    raw_instruction = request.resolved_instruction()
    if not raw_instruction:
        raise HTTPException(status_code=422, detail="Provide 'instruction' or 'operator_instruction'.")

    # If Twilio transport is active, resolve the customer's real phone number from
    # the Excel directory so call_target is a valid E.164 number, not "mock-customer".
    if settings.enable_twilio_transport:
        try:
            prepared = await prep_service.prepare_from_instruction(raw_instruction)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        session = await session_service.create_session(
            raw_instruction,
            call_target=prepared.customer_record.phone_number,
        )
        # Enrich the session with the customer-aware parsed intent and greeting
        session.parsed_intent = prepared.parsed_intent
        session.agent_last_message = prepared.personalized_message
    else:
        session = await session_service.create_session(raw_instruction, request.call_target)

    try:
        session = await session_service.start_session(session)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return session.model_dump()


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    session = registry.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.model_dump()


@app.post("/sessions/{session_id}/turns")
async def handle_turn(session_id: str, request: CustomerTurnRequest):
    session = registry.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session = await session_service.handle_customer_turn(session, request.customer_message)
    return session.model_dump()
