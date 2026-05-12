# Outbound Assistant

Minimal telephony-first PoC for an AI outbound caller. The first milestone is a working vertical slice that can:

- parse an unstructured operator instruction
- create a session and initiate a mocked outbound call
- run a graph-driven conversation loop
- handle basic escalation
- persist transcript, summary, outcome, and errors

## Run

1. Create a virtual environment and install `requirements.txt`.
2. Copy `.env.example` to `.env`.
3. Launch the API:

```bash
uvicorn app.api.fastapi_app:app --reload
```

4. Launch the debug UI:

```bash
python -m app.main
```

## Notes

- `TelnyxTransport` is intentionally mocked for the first pass but follows the transport contract needed for a live adapter.
- Gradio is a debug transport, not the core runtime abstraction.
- The conversation engine uses LangGraph with separate call and conversation state.
