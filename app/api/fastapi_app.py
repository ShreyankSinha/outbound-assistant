from __future__ import annotations

import logging
from contextlib import asynccontextmanager

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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared registry — one instance for the lifetime of the process.
# ---------------------------------------------------------------------------
registry = SessionRegistry()

# ---------------------------------------------------------------------------
# Module-level references updated by _init_services().
# Tests reach these via `import app.api.fastapi_app as fa` → fa.session_service
# ---------------------------------------------------------------------------
session_service: SessionService
prep_service: OutboundPrepService


def _init_services() -> None:
    """
    Clear the settings LRU-cache, re-read .env, and (re)build every service
    that depends on the transport.  Called at app startup via the lifespan so
    the server always honours whatever is currently in .env — even if .env was
    absent or changed before the previous cold-start.
    """
    global session_service, prep_service

    get_settings.cache_clear()
    s = get_settings()

    transport: GradioTransport | TwilioTransport
    if s.enable_twilio_transport:
        transport = TwilioTransport()
    else:
        transport = GradioTransport()

    print(
        f"[STARTUP] transport={type(transport).__name__}  "
        f"enable_twilio_transport={s.enable_twilio_transport}  "
        f"twilio_status_callback_url={s.twilio_status_callback_url!r}"
    )
    logger.info(
        "[STARTUP] transport=%s  enable_twilio_transport=%s",
        type(transport).__name__,
        s.enable_twilio_transport,
    )

    session_service = SessionService(transport, registry)
    prep_service = OutboundPrepService(CustomerDirectory(), session_service)


# Seed with GradioTransport so the module is importable before the lifespan
# fires (needed when tests import the module and TestClient triggers lifespan).
_init_services()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Re-initialise with fresh .env on every server startup.
    _init_services()
    yield


# ---------------------------------------------------------------------------
# App — router uses a thin proxy so it always delegates to the *current*
# session_service global (set by lifespan), not the import-time seed.
# ---------------------------------------------------------------------------
class _SessionServiceProxy:
    """Delegates every attribute lookup to the live session_service global."""

    def __getattr__(self, name: str):  # noqa: ANN204
        return getattr(session_service, name)


_proxy = _SessionServiceProxy()

app = FastAPI(title="Outbound Assistant", lifespan=lifespan)
app.include_router(create_twilio_router(_proxy))  # type: ignore[arg-type]
app.include_router(create_twilio_ws_router())


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sessions")
async def create_session(request: StartSessionRequest):
    raw_instruction = request.resolved_instruction()
    if not raw_instruction:
        raise HTTPException(status_code=422, detail="Provide 'instruction' or 'operator_instruction'.")

    current_settings = get_settings()

    print(
        f"[POST /sessions] enable_twilio_transport={current_settings.enable_twilio_transport}  "
        f"transport={type(session_service.voice.transport).__name__}"
    )

    if current_settings.enable_twilio_transport:
        # Resolve the customer's real E.164 phone number from the Excel directory.
        try:
            prepared = await prep_service.prepare_from_instruction(raw_instruction)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        print(
            f"[POST /sessions] customer_id={prepared.parsed_intent.customer_id}  "
            f"call_target={prepared.customer_record.phone_number!r}"
        )

        session = await session_service.create_session(
            raw_instruction,
            call_target=prepared.customer_record.phone_number,
        )
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
