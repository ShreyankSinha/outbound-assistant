from fastapi import FastAPI, HTTPException, WebSocket
from pydantic import BaseModel

from app.services.session_service import SessionService
from app.transport.telnyx_transport import TelnyxTransport

app = FastAPI(title="Outbound Assistant")
session_service = SessionService(TelnyxTransport())
session_store = {}


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
    session = await session_service.start_session(session)
    session_store[session.session_id] = session
    return session.model_dump()


@app.post("/sessions/{session_id}/turns")
async def handle_turn(session_id: str, request: CustomerTurnRequest):
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session = await session_service.handle_customer_turn(session, request.customer_message)
    session_store[session_id] = session
    return session.model_dump()


@app.post("/webhooks/telnyx")
async def telnyx_webhook(payload: dict):
    return {"received": True, "payload": payload}


@app.websocket("/ws/telnyx")
async def telnyx_media_websocket(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"status": "connected", "message": "Telnyx media websocket stub ready"})
    await websocket.close()
