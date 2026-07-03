from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///./data/agent.db")
    log_level: str = Field(default="INFO")

    # LLM provider — auto-detected from whichever key is set if left blank
    llm_provider: str = Field(default="")   # "anthropic" | "gemini"
    llm_model: str = Field(default="")      # uses provider default when blank

    # Provider keys — set exactly one
    anthropic_api_key: str = Field(default="")
    gemini_api_key: str = Field(default="")

    # Analysis / agent tuning
    sample_rows: int = Field(default=5)              # rows of the dataset sent to the LLM
    sandbox_timeout_seconds: int = Field(default=15) # wall-clock limit for generated code
    max_retries: int = Field(default=3)              # bounded error-fix retries

    # Conversation Intelligence (Phase 4) classifier tuning
    classify_model: str = Field(default="gemini-2.5-flash-lite")  # fast, low-cost model
    classify_batch_size: int = Field(default=15)     # transcripts per Gemini request
    classify_concurrency: int = Field(default=4)     # bounded concurrent batches (legacy alias)
    # Max concurrent Gemini classify batches. Conservative by design: hammering the API
    # at high concurrency provokes 503 "high demand" throttling on 12k-row jobs, so we
    # trade raw speed for reliability. Honoured by the classification semaphore.
    classify_max_concurrency: int = Field(default=4)
    # Transient-error retry-with-backoff (503/UNAVAILABLE, 429/RESOURCE_EXHAUSTED,
    # deadline/timeout/connection). Applied around every Gemini call.
    classify_retry_max_attempts: int = Field(default=5)   # total attempts (incl. first)
    classify_retry_base_delay: float = Field(default=1.0)  # seconds; grows exponentially
    classify_retry_max_delay: float = Field(default=8.0)   # per-attempt backoff cap (s)
    transcript_max_chars: int = Field(default=6000)  # per-transcript truncation
    taxonomy_sample_size: int = Field(default=100)   # transcripts sampled to derive taxonomy
    summary_sample_size: int = Field(default=20)     # transcripts sampled per per-intent summary
    summary_transcript_max_chars: int = Field(default=1200)  # sample truncation for summaries


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
