from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    cartesia_api_key: str = Field(default="", alias="CARTESIA_API_KEY")
    telnyx_api_key: str = Field(default="", alias="TELNYX_API_KEY")
    telnyx_public_webhook_base_url: str = Field(default="", alias="TELNYX_PUBLIC_WEBHOOK_BASE_URL")
    telnyx_connection_id: str = Field(default="", alias="TELNYX_CONNECTION_ID")
    telnyx_outbound_from_number: str = Field(default="", alias="TELNYX_OUTBOUND_FROM_NUMBER")
    telnyx_webhook_secret: str = Field(default="", alias="TELNYX_WEBHOOK_SECRET")
    telnyx_ai_voice: str = Field(default="AWS.Polly.Joanna-Neural", alias="TELNYX_AI_VOICE")
    telnyx_answering_machine_detection: str = Field(default="detect_beep", alias="TELNYX_ANSWERING_MACHINE_DETECTION")
    groq_model_primary: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL_PRIMARY")
    groq_model_fallback: str = Field(default="llama-3.1-8b-instant", alias="GROQ_MODEL_FALLBACK")
    whisper_model_size: str = Field(default="small", alias="WHISPER_MODEL_SIZE")
    cartesia_voice_id: str = Field(default="", alias="CARTESIA_VOICE_ID")
    log_dir: str = Field(default="./logs", alias="LOG_DIR")
    max_turns_before_escalation: int = Field(default=10, alias="MAX_TURNS_BEFORE_ESCALATION")
    max_silence_seconds: int = Field(default=8, alias="MAX_SILENCE_SECONDS")
    llm_timeout_seconds: int = Field(default=20, alias="LLM_TIMEOUT_SECONDS")
    enable_gradio_debug: bool = Field(default=True, alias="ENABLE_GRADIO_DEBUG")
    enable_telnyx_transport: bool = Field(default=False, alias="ENABLE_TELNYX_TRANSPORT")
    fastapi_host: str = Field(default="0.0.0.0", alias="FASTAPI_HOST")
    fastapi_port: int = Field(default=8000, alias="FASTAPI_PORT")
    gradio_server_host: str = Field(default="127.0.0.1", alias="GRADIO_SERVER_HOST")
    gradio_server_port: int = Field(default=7860, alias="GRADIO_SERVER_PORT")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", populate_by_name=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
