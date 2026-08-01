"""ExplainabilityEngine — turns an Alert into an analyst-readable explanation
and a constrained mitigation checklist, via a local LLM (Ollama/Mistral).

RUNS OUT-OF-BAND, NEVER INLINE WITH INGESTION. ``POST /api/v1/log`` persists
alerts with ``explanation``/``mitigation_steps`` left NULL and schedules
``generate_explanation_task`` as a FastAPI ``BackgroundTasks`` job (see
api/logs.py) — this module is what that background task calls. An LLM call
can take several seconds; doing it inline would make ingestion latency
depend on Ollama, which is exactly the kind of coupling that caused the
connection-pool exhaustion problems in earlier phases under bursty load. A
production system would use a real task queue (Celery, arq, etc.) for
retry/observability/backpressure; BackgroundTasks is a reasonable v1 for a
student project and adds no new dependency.

PARSING STRATEGY — delimited text, not JSON, and here's why: local 7B-class
models like Mistral running zero-shot through Ollama are noticeably
unreliable at emitting STRICT JSON on every call — a stray preamble
("Sure, here's the analysis:"), a trailing code fence, a smart-quote instead
of a straight one, or a truncated closing brace are all common, and every
one of those breaks ``json.loads`` outright with no partial credit. A fixed
format with plain-text section markers (``EXPLANATION:`` / ``MITIGATION:``)
degrades much more gracefully: we can still find the markers and extract
what's between them even if the model wraps the answer in extra prose, and
parsing mitigation lines with simple string splitting doesn't require the
whole response to be syntactically valid. Combined with the constrained
mitigation vocabulary (D3) — we only ever accept lines that contain one of a
fixed set of phrases — this gets us most of JSON's structure-safety without
JSON's all-or-nothing fragility against a model that isn't instruction-tuned
for strict JSON output.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai import ollama_client
from app.config import get_settings
from app.models.alert import Alert
from app.models.behavior_profile import BehaviorProfile
from app.models.log_event import LogEvent

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Fixed mitigation vocabulary (D3). The model is asked to select 2-5 of
# these, verbatim, rather than invent its own wording — this keeps
# mitigation_steps structured enough to render as a checklist on a future
# dashboard, and prevents hallucinated/nonsensical recommendations. Parsing
# only ever accepts lines that contain one of these phrases (case-insensitive
# substring match); anything else is dropped rather than trusted.
MITIGATION_VOCABULARY = [
    "block IP",
    "force password reset",
    "require MFA re-enrollment",
    "notify user via secondary channel",
    "temporarily lock account",
    "review recent account activity",
    "no action needed, monitor",
]

_EXPLANATION_MARKER = re.compile(r"EXPLANATION\s*:", re.IGNORECASE)
_MITIGATION_MARKER = re.compile(r"MITIGATION\s*:", re.IGNORECASE)
_BULLET_PREFIX = re.compile(r"^[\s\-\*•\d.\)]+")


def _build_mitigation_prompt_block() -> str:
    options = "\n".join(f'- "{item}"' for item in MITIGATION_VOCABULARY)
    return options


class ExplainabilityEngine:
    """Builds prompts, calls Ollama, parses responses, updates Alert rows."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    # ------------------------------------------------------------- prompt

    def build_prompt(
        self, alert: Alert, event: LogEvent | None, profile: BehaviorProfile | None
    ) -> str:
        """Construct the LLM prompt for one alert (D3).

        Includes: alert type/severity/score (raw AND adjusted, with a note
        when they differ, since that delta is itself meaningful context —
        it means behavioral novelty pushed this alert's severity up from
        what the rule alone would have said); the triggering event's key
        details; and behavioral context from the user's profile. Ends with
        the fixed mitigation vocabulary and an exact output format.
        """
        score_line = f"- Score: {alert.score}/100 ({alert.severity.value})"
        if alert.score != alert.raw_score or alert.severity != alert.raw_severity:
            score_line += (
                f"\n- Note: the detector's original call was "
                f"{alert.raw_score}/100 ({alert.raw_severity.value}). The score was "
                f"adjusted upward because this user's recent behavior is unusual "
                f"(see deviation_score below) — explain briefly why that context "
                f"justifies the escalation."
            )
        else:
            score_line += (
                "\n- Note: this matches the detector's original call exactly — "
                "this user's behavior around this event looked normal, so no "
                "behavioral escalation was applied."
            )

        if event is not None:
            event_block = (
                f"- Event type: {event.event_type.value}\n"
                f"- Source IP: {event.ip}\n"
                f"- Timestamp: {event.timestamp.isoformat()}"
            )
        else:
            event_block = "- (Triggering event details unavailable.)"

        if profile is not None:
            known_ip_count = len(profile.known_ips or [])
            profile_block = (
                f"- Known IPs for this user: {known_ip_count}\n"
                f"- Current deviation score (0.0-1.0, how unusual this event's "
                f"context was vs. this user's baseline): {profile.deviation_score:.2f}\n"
                f"- Rolling user risk score (0-100, cumulative across all this "
                f"user's alerts): {profile.user_risk_score:.1f}\n"
                f"- Total logins observed for this user: {profile.login_count}"
            )
        else:
            profile_block = "- (No behavioral profile available for this user yet.)"

        return f"""You are a security analyst assistant reviewing an intrusion-detection alert.

ALERT
- Type: {alert.alert_type}
{score_line}
- Message: {alert.message}

TRIGGERING EVENT
{event_block}

USER BEHAVIORAL CONTEXT
{profile_block}

TASK
Write a concise, analyst-readable explanation of this alert in 2-4 sentences.
Be specific and grounded in the data above — do not restate the alert
message verbatim, and do not pad with filler. Then select 2-5 mitigation
actions from this fixed list ONLY (do not invent other actions):
{_build_mitigation_prompt_block()}

Respond in EXACTLY this format, with no other text before or after:

EXPLANATION: <your 2-4 sentence explanation>
MITIGATION:
- <action from the list above>: <one-line justification>
- <action from the list above>: <one-line justification>
"""

    # ------------------------------------------------------------- parsing

    def _parse_response(self, raw: str) -> dict | None:
        """Parse a delimited LLM response into {explanation, mitigation_steps}.

        Returns ``None`` on any structural failure (missing markers, empty
        explanation, zero valid mitigation items) — callers must treat that
        as "leave the alert's fields NULL", never store a partial/garbage
        result.
        """
        exp_match = _EXPLANATION_MARKER.search(raw)
        mit_match = _MITIGATION_MARKER.search(raw)
        if not exp_match or not mit_match or mit_match.start() <= exp_match.end():
            return None

        explanation = raw[exp_match.end() : mit_match.start()].strip()
        if not explanation:
            return None

        mitigation_block = raw[mit_match.end() :].strip()
        steps = self._parse_mitigation_lines(mitigation_block)
        if not steps:
            return None

        return {"explanation": explanation, "mitigation_steps": steps}

    @staticmethod
    def _parse_mitigation_lines(block: str) -> list[dict]:
        """Extract mitigation items, accepting only lines that name one of
        the fixed vocabulary phrases (case-insensitive substring match).
        Anything else — hallucinated actions, stray prose — is dropped
        rather than trusted, per D3.
        """
        steps: list[dict] = []
        for raw_line in block.splitlines():
            line = _BULLET_PREFIX.sub("", raw_line).strip().strip('"')
            if not line:
                continue

            matched_action = next(
                (
                    vocab_item
                    for vocab_item in MITIGATION_VOCABULARY
                    if vocab_item.lower() in line.lower()
                ),
                None,
            )
            if matched_action is None:
                continue

            # Whatever's left after the action phrase (past a ':' or '-'
            # separator, if present) is the justification.
            remainder = re.sub(re.escape(matched_action), "", line, count=1, flags=re.IGNORECASE)
            justification = remainder.lstrip(" :-–—").strip()

            steps.append({"action": matched_action, "justification": justification or None})
            if len(steps) >= 5:
                break

        return steps

    # --------------------------------------------------------------- main

    async def explain(self, alert_id: UUID) -> None:
        """Fetch fresh state for ``alert_id``, generate, parse, persist.

        Fetches everything fresh from the DB rather than assuming any
        objects passed in are still attached — this runs in a background
        task, likely with a different session than the one that created the
        alert, which may already be closed by the time this executes.
        """
        alert = self.db.query(Alert).filter(Alert.id == alert_id).one_or_none()
        if alert is None:
            logger.warning("generate_explanation_task: alert %s not found, skipping", alert_id)
            return

        event = None
        if alert.triggered_by_event_id is not None:
            event = (
                self.db.query(LogEvent)
                .filter(LogEvent.id == alert.triggered_by_event_id)
                .one_or_none()
            )

        profile = (
            self.db.query(BehaviorProfile)
            .filter(BehaviorProfile.user_id == alert.user_id)
            .one_or_none()
        )

        prompt = self.build_prompt(alert, event, profile)

        raw_response = await ollama_client.generate(prompt, timeout=self.settings.LLM_TIMEOUT_SECONDS)
        if raw_response is None:
            # ollama_client already logged the specific failure reason.
            # Nothing to do — explanation/mitigation_steps are already NULL
            # from alert creation.
            logger.info("No explanation generated for alert %s (Ollama unavailable)", alert_id)
            return

        parsed = self._parse_response(raw_response)
        if parsed is None:
            logger.warning(
                "Could not parse Ollama response for alert %s, leaving fields NULL. Raw response: %s",
                alert_id,
                raw_response[:1000],
            )
            return

        alert.explanation = parsed["explanation"]
        alert.mitigation_steps = parsed["mitigation_steps"]
        self.db.add(alert)
        self.db.commit()
        logger.info("Explanation generated for alert %s", alert_id)


# ---------------------------------------------------------- background task


async def generate_explanation_task(alert_id: UUID, db_session_factory: "Callable[[], Session]") -> None:
    """Entry point for ``BackgroundTasks.add_task`` (see api/logs.py).

    Creates and closes its own DB session — background tasks run after the
    request has already returned, so the request's session may be closed by
    the time this executes. Never propagates an exception: a failure here
    must not take down the worker or surface to a client that has already
    gotten its response.

    TODO(future phase): no retry-with-backoff here. A transient Ollama
    hiccup just means this alert stays unexplained; a real task queue
    (Celery/arq) would let us retry a bounded number of times instead.
    """
    db = db_session_factory()
    try:
        engine = ExplainabilityEngine(db)
        await engine.explain(alert_id)
    except Exception:  # noqa: BLE001 - background task boundary, must never raise
        logger.exception("generate_explanation_task failed for alert %s", alert_id)
    finally:
        db.close()
