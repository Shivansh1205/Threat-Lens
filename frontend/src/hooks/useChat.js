import { useCallback, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8002";

function generateId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Chat session state for the ChatWidget. `session_id` is generated once,
 * client-side, and kept only for the component tree's lifetime (React
 * state) — no localStorage/persistence across reloads in this phase, per
 * the design notes. The backend keeps its own conversation history keyed
 * by this same session_id (see app/ai/chatbot.py), so a reload starting a
 * fresh session_id just means a fresh conversation server-side too, which
 * is consistent behavior.
 */
export function useChat() {
  const [sessionId] = useState(generateId);
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const sendMessage = useCallback(
    async (text) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      setMessages((prev) => [...prev, { id: generateId(), role: "user", text: trimmed }]);
      setIsLoading(true);
      setError(null);

      try {
        const res = await fetch(`${API_URL}/api/v1/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, message: trimmed }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        // NOTE: the backend's honest "I'm unable to reach the AI assistant
        // right now" fallback (graceful degradation when Ollama is down)
        // arrives here too — as a normal 200 response with a real
        // `response` string. It's handled identically to any other reply;
        // it is NOT an error from this hook's point of view, and
        // ChatWidget renders it as a standard assistant bubble, not an
        // error one. Only a genuine fetch/network/HTTP failure below sets
        // `isError`.
        setMessages((prev) => [...prev, { id: generateId(), role: "assistant", text: data.response }]);
      } catch (err) {
        setError(err.message);
        setMessages((prev) => [
          ...prev,
          {
            id: generateId(),
            role: "assistant",
            text: "Something went wrong reaching the server. Please try again.",
            isError: true,
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId]
  );

  return { messages, sendMessage, isLoading, error };
}
