"""Application configuration, loaded from environment variables / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object. Read once, cached, imported everywhere else.

    Values are sourced from the environment, falling back to `.env` in the
    backend/ directory. See `.env.example` for the full list of variables.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Core app ---
    APP_NAME: str = "ThreatLens"
    ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # --- Database ---
    DATABASE_URL: str = "postgresql://user:pass@localhost:5432/threatlens"
    # Connection pool sizing. Default 5+10 overflow gets saturated by bursty
    # ingestion (e.g. generate_logs.py --speed 100), producing
    # sqlalchemy.exc.TimeoutError / 500s. Ignored by SQLite (used in tests).
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40

    # --- Auth ---
    JWT_SECRET: str = "change-me"

    # --- LLM / explainability layer (Phase 5) ---
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "mistral"

    # --- Detection thresholds (Phase 3) ---
    # Brute-force login detection: sliding window keyed by user_id.
    BRUTE_FORCE_WINDOW_SECONDS: int = 60
    BRUTE_FORCE_MEDIUM_THRESHOLD: int = 5
    BRUTE_FORCE_HIGH_THRESHOLD: int = 10
    BRUTE_FORCE_CRITICAL_THRESHOLD: int = 20

    # Port-scan detection: sliding window keyed by source IP.
    PORT_SCAN_WINDOW_SECONDS: int = 3
    PORT_SCAN_HIGH_THRESHOLD: int = 15
    PORT_SCAN_CRITICAL_THRESHOLD: int = 50

    # Unusual-IP detection: how many login events establish the known-IP set
    # before we start flagging new IPs.
    UNUSUAL_IP_BOOTSTRAP_COUNT: int = 3

    # --- Behavior profiling (Phase 4) ---
    # Smoothing factor for every EMA computation in BehaviorProfiler (login
    # hour, login-hour variance, days-between-logins, session duration). One
    # alpha for all of them, on purpose — don't invent per-metric alphas.
    EMA_ALPHA: float = 0.05


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance so env parsing happens once."""
    return Settings()
