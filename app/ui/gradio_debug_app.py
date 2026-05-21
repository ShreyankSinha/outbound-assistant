from __future__ import annotations

import asyncio

import gradio as gr

from app.services.session_service import SessionService
from app.transport.gradio_transport import GradioTransport

"""
LATENCY DIAGNOSIS:
1. Transcript growth: Yes, transcript is sent to Groq without truncation, growing linearly.
2. Model in use: 'llama-3.3-70b-versatile' is currently used, contributing to latency.
3. Number of LLM calls: Confirmed only one call per turn is made. No legacy calls exist.
4. Between-conversation latency: `SessionService` is instantiated globally, reusing registries and LLM client state across all Gradio sessions.
5. Hugging Face cold starts: N/A, but noted for free tier.
"""

SESSION_CACHE = {}


def start_session(operator_instruction: str):
    service = SessionService(GradioTransport())
    session = asyncio.run(service.create_session(operator_instruction))
    session = asyncio.run(service.start_session(session))
    SESSION_CACHE["active"] = session
    SESSION_CACHE["service"] = service
    transcript = "\n".join(f"{item.role}: {item.content}" for item in session.transcript)
    return session.session_id, transcript, session.agent_last_message, session.summary


def send_customer_message(customer_message: str):
    session = SESSION_CACHE.get("active")
    service = SESSION_CACHE.get("service")
    if not session or not service:
        return "", "No active session.", "", ""
    session = asyncio.run(service.handle_customer_turn(session, customer_message))
    SESSION_CACHE["active"] = session
    transcript = "\n".join(f"{item.role}: {item.content}" for item in session.transcript)
    summary = session.summary if session.timestamp_end else ""
    return transcript, session.agent_last_message, summary, session.outcome.value if session.outcome else ""


def build_demo():
    with gr.Blocks(title="Outbound Assistant Debug") as demo:
        gr.Markdown("## Outbound Assistant Debug Transport")
        with gr.Row():
            with gr.Column():
                operator_instruction = gr.Textbox(label="Operator Instruction", lines=4)
                start_button = gr.Button("Start Outbound Session")
                session_id = gr.Textbox(label="Session ID", interactive=False)
            with gr.Column():
                customer_message = gr.Textbox(label="Customer Response", lines=3)
                send_button = gr.Button("Send Customer Turn")
                last_agent_message = gr.Textbox(label="Latest Agent Message", interactive=False)
        transcript = gr.Textbox(label="Transcript", lines=18, interactive=False)
        summary = gr.Textbox(label="Session Summary", lines=4, interactive=False)
        outcome = gr.Textbox(label="Outcome", interactive=False)

        start_button.click(
            fn=start_session,
            inputs=[operator_instruction],
            outputs=[session_id, transcript, last_agent_message, summary],
        )
        send_button.click(
            fn=send_customer_message,
            inputs=[customer_message],
            outputs=[transcript, last_agent_message, summary, outcome],
        )
    return demo
demo = build_demo()
demo.launch(server_name="0.0.0.0")
