from __future__ import annotations

import asyncio

import gradio as gr

from app.services.session_service import SessionService
from app.transport.gradio_transport import GradioTransport

service = SessionService(GradioTransport())
SESSION_CACHE = {}


def start_session(operator_instruction: str):
    session = asyncio.run(service.create_session(operator_instruction))
    session = asyncio.run(service.start_session(session))
    SESSION_CACHE["active"] = session
    transcript = "\n".join(f"{item.role}: {item.content}" for item in session.transcript)
    return session.session_id, transcript, session.agent_last_message, session.summary


def send_customer_message(customer_message: str):
    session = SESSION_CACHE.get("active")
    if not session:
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
