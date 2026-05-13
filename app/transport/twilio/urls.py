from __future__ import annotations


def twilio_webhook_urls_from_status_callback(status_callback_url: str) -> tuple[str, str, str]:
    base = status_callback_url.rstrip("/").rsplit("/", 1)[0]
    voice = f"{base}/voice"
    action = f"{base}/action"
    return voice, status_callback_url.strip(), action
