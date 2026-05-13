from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.api.routes_twilio_webhooks import create_twilio_router
from app.api.routes_twilio_ws import create_twilio_ws_router
from app.config import get_settings
from app.core.exceptions import ProviderError
from app.services.session_service import SessionService
from app.services.session_registry import SessionRegistry
from app.transport.gradio_transport import GradioTransport
from app.transport.twilio_transport import TwilioTransport

app = FastAPI(title="Outbound Assistant")
settings = get_settings()
registry = SessionRegistry()
transport = TwilioTransport() if settings.enable_twilio_transport else GradioTransport()
session_service = SessionService(transport, registry)

app.include_router(create_twilio_router(session_service))
app.include_router(create_twilio_ws_router())


class StartSessionRequest(BaseModel):
    operator_instruction: str
    call_target: str = "mock-customer"


class CustomerTurnRequest(BaseModel):
    customer_message: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sessions")
async def create_session(request: StartSessionRequest):
    session = await session_service.create_session(request.operator_instruction, request.call_target)
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
