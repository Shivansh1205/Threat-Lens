"""Application configuration, loaded from environment variables / .env."""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

    # --- CORS ---
    # Origins allowed to call the API from a browser (frontend dev server,
    # plus the 127.0.0.1 alias browsers sometimes resolve localhost to).
    # `NoDecode` matters here: pydantic-settings v2 normally tries to
    # JSON-decode env values for "complex" types like list[str] *before*
    # any validator runs, so a plain comma-separated string in .env
    # (e.g. `CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`)
    # would fail with a SettingsError ("Expecting value") rather than
    # silently doing the wrong thing. NoDecode disables that JSON-decode
    # attempt so the raw string reaches the validator below untouched;
    # a JSON array string (`["http://...", "http://..."]`) still works too,
    # since the validator only splits when it actually receives a str.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # --- Database ---
    DATABASE_URL: str = "postgresql://user:pass@localhost:5432/threatlens"
    # Connection pool sizing. Default 5+10 overflow gets saturated by bursty
    # ingestion (e.g. generate_logs.py --speed 100), producing
    # sqlalchemy.exc.TimeoutError / 500s. Ignored by SQLite (used in tests).
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40

    # --- Auth ---
    JWT_SECRET: str = "change-me"

    # --- LLM / explainability layer (Phase 6) ---
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "mistral"
    # Strict timeout for any single Ollama call (explanation generation or
    # chatbot reply). Local 7B-class models on modest hardware can take
    # several seconds; if this is exceeded, the caller treats it as a
    # failure and degrades gracefully (see app/ai/ollama_client.py) rather
    # than hanging the background task or the chat request indefinitely.
    LLM_TIMEOUT_SECONDS: float = 15.0

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
    # Decay here is applied once per NEW ALERT EVENT for this user, not once
    # per elapsed unit of time. See DAILY_DECAY_RATE below for the
    # complementary time-based decay that closes that gap — this constant
    # and that one are deliberately separate mechanisms; this per-event decay
    # is unchanged.
    RISK_CONTRIBUTION_WEIGHT: float = 0.15
    USER_RISK_DECAY_FACTOR: float = 0.995

    # --- Time-based risk decay (closes the Phase 4/5 "decay is per-event
    # only" follow-up — see app/scoring/decay_job.py and PHASES.md) ---
    # Applied by a scheduled job, independent of whether the user triggers
    # any new alerts: decayed = score * (DAILY_DECAY_RATE ** days_elapsed).
    # 0.98 roughly halves an untouched score in ~34 days (0.98**34 ≈ 0.5) —
    # old suspicious behavior stops mattering after about a month without a
    # flag vanishing overnight. This is additive to, not a replacement for,
    # USER_RISK_DECAY_FACTOR above.
    DAILY_DECAY_RATE: float = 0.98

    # How often the scheduled decay job runs. An interval rather than a
    # fixed wall-clock time (e.g. "run at 03:00") — simpler, avoids timezone
    # questions, adequate at this project's scale. A production deployment
    # would likely prefer a fixed low-traffic hour instead of a rolling
    # interval, so restarts don't drift the schedule.
    DECAY_JOB_INTERVAL_HOURS: float = 24.0

    # Below this, a profile's user_risk_score is clamped to exactly 0.0
    # rather than left to decay asymptotically forever (and profiles at or
    # below this are skipped entirely — no point processing/writing rows
    # that are already effectively zero).
    DECAY_SCORE_FLOOR: float = 0.01


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance so env parsing happens once."""
    return Settings()
