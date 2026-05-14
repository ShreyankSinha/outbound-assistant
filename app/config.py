from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model_primary: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL_PRIMARY")
    groq_model_fallback: str = Field(default="llama-3.1-8b-instant", alias="GROQ_MODEL_FALLBACK")
    log_dir: str = Field(default="./logs", alias="LOG_DIR")
    max_turns_before_escalation: int = Field(default=10, alias="MAX_TURNS_BEFORE_ESCALATION")
    max_silence_seconds: int = Field(default=8, alias="MAX_SILENCE_SECONDS")
    llm_timeout_seconds: int = Field(default=20, alias="LLM_TIMEOUT_SECONDS")
    enable_gradio_debug: bool = Field(default=True, alias="ENABLE_GRADIO_DEBUG")
    enable_twilio_transport: bool = Field(default=False, alias="ENABLE_TWILIO_TRANSPORT")
    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_phone_number: str = Field(default="", alias="TWILIO_PHONE_NUMBER")
    twilio_status_callback_url: str = Field(default="", alias="TWILIO_STATUS_CALLBACK_URL")
    twilio_stream_url: str = Field(default="", alias="TWILIO_STREAM_URL")
    twilio_skip_sig_validation: bool = Field(default=False, alias="TWILIO_SKIP_SIG_VALIDATION")
    twilio_simulation_mode: bool = Field(default=False, alias="TWILIO_SIMULATION_MODE")
    fastapi_host: str = Field(default="0.0.0.0", alias="FASTAPI_HOST")
    fastapi_port: int = Field(default=8000, alias="FASTAPI_PORT")
    gradio_server_host: str = Field(default="127.0.0.1", alias="GRADIO_SERVER_HOST")
    gradio_server_port: int = Field(default=7860, alias="GRADIO_SERVER_PORT")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", populate_by_name=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
