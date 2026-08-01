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

    # --- Severity bucketing (Phase 3/4/5) ---
    # Centralized here so RiskScorer's post-adjustment re-bucketing uses the
    # EXACT same boundaries as everything else (ARCHITECTURE.md's "Dynamic
    # Risk Scoring" section). Inclusive upper bounds; CRITICAL is anything
    # above SEVERITY_HIGH_MAX. See app/scoring/risk_scorer.severity_for_score.
    SEVERITY_LOW_MAX: int = 25
    SEVERITY_MEDIUM_MAX: int = 50
    SEVERITY_HIGH_MAX: int = 75

    # --- Dynamic risk scoring (Phase 5) ---
    # How much a user's current behavioral deviation_score (0.0-1.0) can push
    # a detector's raw alert score toward 100. Scaled by remaining headroom
    # (100 - base_score) so it can meaningfully escalate a borderline alert
    # without catapulting a low-severity one straight to CRITICAL. See
    # app/scoring/risk_scorer.RiskScorer.score_alert.
    DEVIATION_WEIGHT: float = 0.3

    # Rolling per-user risk score (BehaviorProfile.user_risk_score): how much
    # weight one alert's adjusted score contributes to the cumulative score,
    # and how much of the previous cumulative score survives each update.
    # Decay is applied once per NEW ALERT EVENT for this user, not once per
    # elapsed unit of time — a "proper" time-based decay (independent of
    # whether new events arrive) needs a scheduled job and is a documented
    # Phase 5.5/6+ follow-up (see PHASES.md). Do not read this as calendar
    # decay.
    RISK_CONTRIBUTION_WEIGHT: float = 0.15
    USER_RISK_DECAY_FACTOR: float = 0.995


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance so env parsing happens once."""
    return Settings()
