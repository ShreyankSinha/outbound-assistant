from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from twilio.request_validator import RequestValidator

from app.config import get_settings
from app.services.session_service import SessionService


def _flatten_form(form: Any) -> dict[str, str]:
    data: dict[str, str] = {}
    for key in form.keys():
        val = form.get(key)
        data[key] = val if isinstance(val, str) else (str(val) if val is not None else "")
    return data


async def _require_valid_twilio_signature(request: Request, params: dict[str, str]) -> None:
    settings = get_settings()
    if settings.twilio_skip_sig_validation:
        return
    token = settings.twilio_auth_token
    if not token:
        raise HTTPException(status_code=500, detail="TWILIO_AUTH_TOKEN is not configured")
    sig = request.headers.get("X-Twilio-Signature") or ""
    validator = RequestValidator(token)
    url = str(request.url)
    if not validator.validate(url, params, sig):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


def create_twilio_router(session_service: SessionService) -> APIRouter:
    router = APIRouter(prefix="/webhooks/twilio", tags=["twilio"])

    @router.post("/status")
    async def twilio_status(request: Request) -> dict[str, bool]:
        form = await request.form()
        params = _flatten_form(form)
        await _require_valid_twilio_signature(request, params)
        await session_service.handle_twilio_status(params)
        return {"ok": True}

    @router.api_route("/voice", methods=["GET", "POST"])
    async def twilio_voice(request: Request) -> Response:
        if request.method == "POST":
            form = await request.form()
            params = _flatten_form(form)
        else:
            params = {}
        for key, value in request.query_params.multi_items():
            params[key] = value
        await _require_valid_twilio_signature(request, params)
        sid = params.get("session_id") or request.query_params.get("session_id")
        if not sid:
            raise HTTPException(status_code=400, detail="session_id is required")
        session = session_service.registry.get(sid)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        twiml = session_service.build_twilio_voice_twiml(session)
        session_service.registry.save(session)
        return Response(content=twiml, media_type="application/xml")

    @router.post("/action")
    async def twilio_gather_action(request: Request) -> Response:
        form = await request.form()
        params = _flatten_form(form)
        for key, value in request.query_params.multi_items():
            params.setdefault(key, value)
        await _require_valid_twilio_signature(request, params)
        _, twiml = await session_service.handle_twilio_gather(params)
        return Response(content=twiml, media_type="application/xml")

    return router
