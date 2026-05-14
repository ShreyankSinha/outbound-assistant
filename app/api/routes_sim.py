"""
app/api/routes_sim.py

Trial-account call simulation endpoints.  These three routes implement a
self-contained conversation loop that requires no physical participant:

  /outbound-call          ← TwiML app entry point; plays agent greeting
  /simulate-customer      ← plays a hardcoded customer reply via TTS
  /handle-customer-response ← receives Twilio STT transcript, runs LangGraph

Activated by setting TWILIO_SIMULATION_MODE=true in .env.
The call is placed FROM and TO the same Twilio number so the TwiML app
intercepts it (works on trial accounts).

Global state
------------
ACTIVE_SCENARIO   str
    Key into SIMULATED_RESPONSES; controls which customer reply is played.
    Set programmatically before triggering a call (or default is used).

SIMULATED_RESPONSES   dict[str, str]
    Extend this dict to add new test scenarios without touching route logic.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response
from twilio.twiml.voice_response import Gather, VoiceResponse

from app.config import get_settings
from app.services.session_service import SessionService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Simulation globals — set ACTIVE_SCENARIO before placing a call to control
# which customer reply plays.
# ---------------------------------------------------------------------------
ACTIVE_SCENARIO: str = "invoice_resend"

SIMULATED_RESPONSES: dict[str, str] = {
    "invoice_resend": (
        "Yes I would like to pay that but I have misplaced the invoice, "
        "can I get it resent to my email please"
    ),
    "already_paid": (
        "I actually already paid that last week, can you check your records"
    ),
    "dispute": (
        "I was unhappy with the service and I do not think I should have to pay"
    ),
}

# Voice constants — keep distinct so agent and customer are easy to tell apart
# in recordings / transcripts.
AGENT_VOICE = "Polly.Matthew"
CUSTOMER_VOICE = "Polly.Joanna"


# ---------------------------------------------------------------------------
# Helper: Twilio signature validation (reuses the existing logic / setting)
# ---------------------------------------------------------------------------
async def _check_sig(request: Request, params: dict[str, str]) -> None:
    from twilio.request_validator import RequestValidator

    settings = get_settings()
    if settings.twilio_skip_sig_validation:
        return
    token = settings.twilio_auth_token
    if not token:
        raise HTTPException(status_code=500, detail="TWILIO_AUTH_TOKEN is not configured")
    sig = request.headers.get("X-Twilio-Signature") or ""
    validator = RequestValidator(token)
    if not validator.validate(str(request.url), params, sig):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


def _flatten(form) -> dict[str, str]:  # noqa: ANN001
    return {k: (v if isinstance(v, str) else str(v) if v is not None else "") for k, v in form.items()}


# ---------------------------------------------------------------------------
# Router factory — receives the session_service proxy from fastapi_app.py
# so it always delegates to the live instance (same pattern as the existing
# Twilio webhook router).
# ---------------------------------------------------------------------------
def create_sim_router(session_service: SessionService) -> APIRouter:  # type: ignore[type-arg]
    router = APIRouter(tags=["simulation"])

    # ------------------------------------------------------------------
    # 1. /outbound-call  — TwiML app entry point
    #
    # Twilio POSTs here when the outbound call is answered (i.e. when our
    # own number picks up the call placed by create_outbound_call in sim
    # mode).  We:
    #   a) bind CallSid → session so status callbacks work
    #   b) play the agent's greeting message
    #   c) redirect to /simulate-customer to play the customer reply
    # ------------------------------------------------------------------
    @router.api_route("/outbound-call", methods=["GET", "POST"])
    async def outbound_call(request: Request) -> Response:
        # Collect params from both form body and query string
        params: dict[str, str] = {}
        if request.method == "POST":
            form = await request.form()
            params = _flatten(form)
        for k, v in request.query_params.multi_items():
            params.setdefault(k, v)

        await _check_sig(request, params)

        session_id = params.get("session_id") or request.query_params.get("session_id")
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")

        session = session_service.registry.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

        # Bind the real CallSid so status-callback events can find this session
        call_sid = params.get("CallSid")
        if call_sid and not session.call_control_id:
            session_service.registry.bind_call_leg(session, call_sid, None)
            logger.info("[SIM] bound CallSid=%s to session_id=%s", call_sid, session_id)

        agent_message = session.agent_last_message or "Hello, this is a follow-up call."

        print(
            f"[SIM /outbound-call] session_id={session_id}  "
            f"CallSid={call_sid}  agent_message={agent_message!r}"
        )

        # Build TwiML: speak the greeting, then redirect to /simulate-customer
        vr = VoiceResponse()
        vr.say(agent_message, voice=AGENT_VOICE)
        vr.redirect(
            f"{session.twilio_simulation_url_absolute.rsplit('/outbound-call', 1)[0]}"
            f"/simulate-customer?session_id={session_id}",
            method="POST",
        )
        return Response(content=str(vr), media_type="application/xml")

    # ------------------------------------------------------------------
    # 2. /simulate-customer  — plays a hardcoded customer reply
    #
    # The <Say> is placed INSIDE a <Gather> so Twilio STT transcribes its
    # own TTS output.  The SpeechResult is then POSTed to
    # /handle-customer-response by Twilio, which runs the LangGraph agent.
    # ------------------------------------------------------------------
    @router.api_route("/simulate-customer", methods=["GET", "POST"])
    async def simulate_customer(request: Request) -> Response:
        params: dict[str, str] = {}
        if request.method == "POST":
            form = await request.form()
            params = _flatten(form)
        for k, v in request.query_params.multi_items():
            params.setdefault(k, v)

        await _check_sig(request, params)

        session_id = params.get("session_id") or request.query_params.get("session_id")
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")

        session = session_service.registry.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

        scenario = ACTIVE_SCENARIO
        customer_text = SIMULATED_RESPONSES.get(
            scenario,
            "I am not sure about this, can you explain?",
        )

        # Derive base URL from simulation URL stored on session
        base = session.twilio_simulation_url_absolute.rsplit("/outbound-call", 1)[0]
        action_url = f"{base}/handle-customer-response?session_id={session_id}"

        print(
            f"[SIM /simulate-customer] session_id={session_id}  "
            f"scenario={scenario!r}  customer_text={customer_text!r}"
        )

        # <Gather> wrapping <Say> — Twilio speaks the text and STT captures it
        vr = VoiceResponse()
        gather = Gather(
            input="speech",
            action=action_url,
            method="POST",
            speech_timeout="auto",
            language="en-US",
        )
        gather.say(customer_text, voice=CUSTOMER_VOICE)
        vr.append(gather)
        # Fallback if Gather times out without capturing anything
        vr.say("I did not hear a response. Goodbye.", voice=AGENT_VOICE)
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")

    # ------------------------------------------------------------------
    # 3. /handle-customer-response  — receives STT transcript, runs agent
    #
    # Twilio POSTs SpeechResult here after capturing what was played in
    # /simulate-customer.  The transcript is fed into the existing
    # session_service.apply_customer_speech() which runs the LangGraph
    # state machine exactly as a real call would.  After one turn the
    # agent plays its response and the call ends cleanly.
    # ------------------------------------------------------------------
    @router.post("/handle-customer-response")
    async def handle_customer_response(request: Request) -> Response:
        form = await request.form()
        params = _flatten(form)
        for k, v in request.query_params.multi_items():
            params.setdefault(k, v)

        await _check_sig(request, params)

        session_id = params.get("session_id") or request.query_params.get("session_id")
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")

        session = session_service.registry.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

        speech = (params.get("SpeechResult") or "").strip()

        print(
            f"[SIM /handle-customer-response] session_id={session_id}  "
            f"SpeechResult={speech!r}"
        )

        if not speech:
            # Nothing was transcribed — close gracefully
            logger.warning("[SIM] empty SpeechResult for session_id=%s", session_id)
            vr = VoiceResponse()
            vr.say("I did not catch that. Goodbye.", voice=AGENT_VOICE)
            vr.hangup()
            return Response(content=str(vr), media_type="application/xml")

        # Run the existing LangGraph agent with the simulated customer speech
        session = await session_service.apply_customer_speech(session, speech)
        session_service.registry.save(session)

        agent_reply = session.agent_last_message or "Thank you. Goodbye."

        print(
            f"[SIM /handle-customer-response] agent_reply={agent_reply!r}  "
            f"conversation_state={session.conversation_state}"
        )

        # Finalise the session (logs to logs/, marks ended)
        await session_service.finalize_session(session, end_call=False)

        # Play agent response and hang up — one-turn simulation complete
        vr = VoiceResponse()
        vr.say(agent_reply, voice=AGENT_VOICE)
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")

    return router
