from __future__ import annotations

from twilio.twiml.voice_response import Gather, VoiceResponse


def build_amd_wait_twiml(*, next_url_absolute: str, pause_seconds: int = 1) -> str:
    vr = VoiceResponse()
    vr.pause(length=pause_seconds)
    vr.redirect(method="POST", url=next_url_absolute)
    return str(vr)


def build_opening_gather_twiml(
    *,
    opening_text: str,
    gather_action_url_absolute: str,
    voice: str = "Polly.Joanna-Neural",
    speech_timeout: str = "auto",
) -> str:
    vr = VoiceResponse()
    vr.say(opening_text, voice=voice)
    gather = Gather(
        input="speech",
        action=gather_action_url_absolute,
        method="POST",
        speech_timeout=speech_timeout,
        language="en-US",
    )
    vr.append(gather)
    vr.say("I did not hear anything. Goodbye.", voice=voice)
    return str(vr)


def build_continue_gather_twiml(
    *,
    agent_text: str,
    gather_action_url_absolute: str,
    voice: str = "Polly.Joanna-Neural",
    speech_timeout: str = "auto",
) -> str:
    vr = VoiceResponse()
    vr.say(agent_text, voice=voice)
    gather = Gather(
        input="speech",
        action=gather_action_url_absolute,
        method="POST",
        speech_timeout=speech_timeout,
        language="en-US",
    )
    vr.append(gather)
    vr.say("Thank you. Goodbye.", voice=voice)
    return str(vr)


def build_voicemail_twiml(*, message: str, voice: str = "Polly.Joanna-Neural") -> str:
    vr = VoiceResponse()
    vr.say(message, voice=voice)
    vr.hangup()
    return str(vr)


def build_closing_twiml(*, message: str, voice: str = "Polly.Joanna-Neural") -> str:
    vr = VoiceResponse()
    vr.say(message, voice=voice)
    vr.hangup()
    return str(vr)
