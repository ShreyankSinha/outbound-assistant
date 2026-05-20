---
title: Outbound Assistant
emoji: 📞
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: "6.14.0"
app_file: app/ui/gradio_debug_app.py
pinned: false
---

# Outbound Assistant

A telephony-first proof of concept for an AI-powered outbound caller. This vertical slice demonstrates a working end-to-end pipeline including instruction parsing, call initiation, graph-driven conversation, escalation handling, and full transcript persistence.

## Features

- Parses unstructured operator instructions into structured call plans
- Creates a session and initiates an outbound call via Twilio
- Runs a graph-driven conversation loop using LangGraph
- Handles basic escalation logic
- Persists transcript, summary, outcome, and errors

## Run

1. Create a virtual environment and install dependencies:
```bash
   pip install -r requirements.txt
```
2. Copy `.env.example` to `.env` and fill in your credentials.
3. Launch the API:
```bash
   uvicorn app.api.fastapi_app:app --reload
```
4. Launch the debug UI:
```bash
   python -m app.main
```

## Architecture Notes

- `TwilioTransport` uses Programmable Voice (`<Say>` + `<Gather input="speech">`) and status webhooks for live calls.
- Gradio serves as a debug transport only — it is not the core runtime abstraction.
- The conversation engine uses LangGraph with separate call and conversation state objects.
