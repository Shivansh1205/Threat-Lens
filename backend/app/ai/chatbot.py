"""ChatbotModule — retrieval-augmented chat over recent alerts.

Grounded, not free-floating: every query is answered with a bounded set of
real recent alerts injected into the prompt (D4), so the model is reasoning
about this deployment's actual data rather than general security trivia. If
Ollama is unreachable, the fallback is an honest "I can't reach the AI
assistant" message — never a fabricated answer dressed up as a real one.

Conversation history is an in-memory, module-level dict keyed by
``session_id`` — the same tier as detector sliding windows: ephemeral,
lost on process restart, fine for a single-process student-project
deployment. A real multi-user/multi-process deployment would need this in
Redis or a DB table keyed by session; flagged here as a Phase 7+ persistence
concern rather than solved now, per D4.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.ai import ollama_client
from app.config import get_settings
from app.models.alert import Alert
from app.models.user import User

logger = logging.getLogger(__name__)

# Exchanges (user message + assistant reply) kept per session, oldest
# dropped first once this cap is hit — bounds prompt size regardless of how
# long a conversation runs.
MAX_HISTORY_EXCHANGES = 10

FALLBACK_MESSAGE = (
    "I'm unable to reach the AI assistant right now. Please try again shortly."
)

# session_id -> list of {"user": str, "assistant": str} exchanges, oldest first.
_conversation_history: dict[str, list[dict[str, str]]] = {}


class ChatbotModule:
    """Conversational analyst interface, grounded on real alert data."""

    # ------------------------------------------------------------- context

    def build_context(self, db: Session, user_id: str | None, limit: int = 20) -> str:
        """Fetch recent alerts (optionally filtered by user_id) as compact text.

        This is the "retrieval" half of retrieval-augmented — the model only
        ever sees what's returned here, so it can't answer from alerts it
        was never shown.
        """
        query = db.query(Alert)
        if user_id is not None:
            query = query.filter(Alert.user_id == user_id)
        alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()

        if not alerts:
            scope = f" for user '{user_id}'" if user_id else ""
            return f"No recent alerts{scope}."

        lines = [
            f"- {a.created_at.isoformat()} | {a.alert_type} | {a.severity.value} "
            f"(score {a.score}/100) | user={a.user_id} | {a.message}"
            for a in alerts
        ]
        header = f"Recent alerts{' for user ' + user_id if user_id else ''} (most recent first):"
        return header + "\n" + "\n".join(lines)

    # ------------------------------------------------------ user-id sniffing

    @staticmethod
    def _detect_mentioned_user_id(db: Session, message: str) -> str | None:
        """Basic mention-check: does the message contain a known user_id as a
        substring? Deliberately not real NLU/NER — a small, bounded win for
        v1. Longest match wins, so e.g. "alice2" isn't shadowed by a
        coincidental shorter user_id like "al" also existing in the system.
        """
        known_user_ids = [row[0] for row in db.query(User.user_id).all()]
        message_lower = message.lower()
        matches = [uid for uid in known_user_ids if uid and uid.lower() in message_lower]
        if not matches:
            return None
        return max(matches, key=len)

    # ----------------------------------------------------------- history

    @staticmethod
    def _get_history(session_id: str) -> list[dict[str, str]]:
        return _conversation_history.setdefault(session_id, [])

    @staticmethod
    def _append_history(session_id: str, user_message: str, assistant_reply: str) -> None:
        history = _conversation_history.setdefault(session_id, [])
        history.append({"user": user_message, "assistant": assistant_reply})
        del history[:-MAX_HISTORY_EXCHANGES]  # keep only the last N exchanges

    @staticmethod
    def _format_history(history: list[dict[str, str]]) -> str:
        if not history:
            return "(no prior conversation)"
        return "\n".join(f"User: {h['user']}\nAssistant: {h['assistant']}" for h in history)

    # --------------------------------------------------------------- main

    async def handle_query(self, session_id: str, message: str, db: Session) -> str:
        """Answer one analyst message, grounded on recent alert context."""
        history = self._get_history(session_id)
        mentioned_user_id = self._detect_mentioned_user_id(db, message)
        context = self.build_context(db, mentioned_user_id, limit=20)

        prompt = f"""You are a security analyst assistant for ThreatLens, an intrusion
detection system. Answer the analyst's question using ONLY the alert data
below — if the data doesn't contain the answer, say so rather than
guessing or relying on general security knowledge.

{context}

CONVERSATION SO FAR
{self._format_history(history)}

New question: {message}

Respond with a concise, direct answer (a few sentences, no filler)."""

        settings = get_settings()
        response_text = await ollama_client.generate(prompt, timeout=settings.LLM_TIMEOUT_SECONDS)

        if response_text is None:
            logger.info("Chatbot fallback used for session %s (Ollama unavailable)", session_id)
            return FALLBACK_MESSAGE

        self._append_history(session_id, message, response_text)
        return response_text
