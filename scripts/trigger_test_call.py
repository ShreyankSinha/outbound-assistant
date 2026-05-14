"""
scripts/trigger_test_call.py

Triggers a test outbound call to Customer ID 1 via the local FastAPI server,
then polls until the call ends or 60 seconds elapse.

Usage (from project root, with .venv activated or via):
    .venv/Scripts/python scripts/trigger_test_call.py

Requirements: FastAPI must be running on http://localhost:8000 with a live ngrok
tunnel and valid Twilio credentials set in .env.
"""
from __future__ import annotations

import sys
import time
import json
import urllib.request
import urllib.error
import urllib.parse

BASE_URL = "http://localhost:8000"
INSTRUCTION = "Customer ID 1 owes $100, call them for payment"
POLL_INTERVAL_SECONDS = 2
MAX_POLL_SECONDS = 60
TERMINAL_STATES = {"ended", "failed"}


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"\n[ERROR] HTTP {exc.code} from POST {url}")
        print(f"        Response body: {body}")
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"\n[ERROR] Could not reach {url}: {exc.reason}")
        print("        Is FastAPI running on port 8000?")
        sys.exit(1)


def get_json(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"[WARN] GET {url} → HTTP {exc.code}: {body[:200]}")
        return None
    except urllib.error.URLError as exc:
        print(f"[WARN] GET {url} failed: {exc.reason}")
        return None


def main() -> None:
    print("=" * 60)
    print("Outbound Assistant — Test Call Trigger")
    print("=" * 60)
    print(f"Instruction : {INSTRUCTION!r}")
    print(f"Target URL  : {BASE_URL}/sessions")
    print()

    # Step 1: Create session (triggers call immediately)
    print("[1/4] POSTing to /sessions ...")
    payload = {"instruction": INSTRUCTION}
    response = post_json(f"{BASE_URL}/sessions", payload)

    session_id = response.get("session_id", "<unknown>")
    call_target = response.get("call_target", "<unknown>")
    call_control_id = response.get("call_control_id")
    parsed_intent = response.get("parsed_intent", {})
    call_state = response.get("call_state", "<unknown>")
    conversation_state = response.get("conversation_state", "<unknown>")

    print(f"\n[2/4] Session created:")
    print(f"  session_id         : {session_id}")
    print(f"  call_target        : {call_target}")
    print(f"  call_control_id    : {call_control_id or '(not yet assigned)'}")
    print(f"  call_state         : {call_state}")
    print(f"  conversation_state : {conversation_state}")
    print(f"  parsed_intent      : customer_id={parsed_intent.get('customer_id')}, "
          f"amount={parsed_intent.get('amount')}, issue_type={parsed_intent.get('issue_type')}")

    if call_control_id:
        print(f"\n  *** Twilio Call SID : {call_control_id} ***")
        print(f"      View at: https://console.twilio.com/us1/monitor/calls")

    # Step 3: Poll for call state changes
    print(f"\n[3/4] Polling /sessions/{session_id} every {POLL_INTERVAL_SECONDS}s (max {MAX_POLL_SECONDS}s) ...")
    print(f"  {'Time':>5}  {'call_state':<20}  {'conversation_state'}")
    print(f"  {'-'*5}  {'-'*20}  {'-'*20}")

    start = time.monotonic()
    elapsed = 0.0
    final_state: dict = response

    while elapsed < MAX_POLL_SECONDS:
        time.sleep(POLL_INTERVAL_SECONDS)
        elapsed = time.monotonic() - start

        data = get_json(f"{BASE_URL}/sessions/{session_id}")
        if data is None:
            print(f"  {elapsed:5.1f}s  [poll failed — will retry]")
            continue

        current_call_state = data.get("call_state", "")
        current_conv_state = data.get("conversation_state", "")
        current_sid = data.get("call_control_id")

        print(f"  {elapsed:5.1f}s  {current_call_state:<20}  {current_conv_state}")

        if current_sid and not call_control_id:
            call_control_id = current_sid
            print(f"         *** Twilio Call SID assigned: {call_control_id} ***")
            print(f"             https://console.twilio.com/us1/monitor/calls")

        final_state = data

        if current_call_state in TERMINAL_STATES:
            print(f"\n  Call reached terminal state: {current_call_state!r}. Stopping poll.")
            break
    else:
        print(f"\n  Polling timed out after {MAX_POLL_SECONDS}s.")

    # Step 4: Final summary
    print("\n[4/4] Final summary:")
    print(f"  session_id         : {session_id}")
    print(f"  call_state         : {final_state.get('call_state', '?')}")
    print(f"  conversation_state : {final_state.get('conversation_state', '?')}")
    print(f"  outcome            : {final_state.get('outcome', '(not yet set)')}")
    print(f"  call_control_id    : {final_state.get('call_control_id') or '(none)'}")
    print(f"  errors             : {final_state.get('errors', [])}")
    print(f"  duration           : ~{elapsed:.0f}s")
    if final_state.get("summary"):
        print(f"  summary            : {final_state['summary']}")

    sid = final_state.get("call_control_id")
    if sid:
        print(f"\n  *** Twilio console: https://console.twilio.com/us1/monitor/calls ***")
        print(f"  *** SID: {sid} ***")

    print("=" * 60)


if __name__ == "__main__":
    main()
