import { useState } from "react";
import { Bot, MessageCircle, Send, User as UserIcon, X } from "lucide-react";
import { useChatContext } from "../../context/ChatContext";

function ChatBubble({ message }) {
  const isUser = message.role === "user";
  // The backend's honest "AI assistant unavailable" fallback (graceful
  // degradation when Ollama is down) arrives as a normal 200 response — a
  // real assistant message, not a client error — so it renders with
  // standard bot-bubble styling below, same as any other reply.
  // `isError` only applies to genuine network/HTTP failures raised
  // client-side (see useChat.js) and gets a visually distinct treatment.
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`flex max-w-[85%] items-start gap-2 ${isUser ? "flex-row-reverse" : ""}`}>
        <span className="mt-0.5 shrink-0 text-slate-500">
          {isUser ? <UserIcon className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
        </span>
        <p
          className={`rounded-lg px-3 py-2 text-sm ${
            isUser
              ? "bg-sky-600 text-white"
              : message.isError
                ? "border border-red-500/30 bg-red-950/40 text-red-200"
                : "bg-slate-800 text-slate-200"
          }`}
        >
          {message.text}
        </p>
      </div>
    </div>
  );
}

/**
 * Collapsible chat panel over POST /api/v1/chat. Starts expanded since it
 * sits in its own dedicated column next to the alert feed in this layout.
 * Reads shared conversation state from ChatContext (see context/ChatContext.jsx)
 * rather than owning its own — the same conversation is visible on the
 * full-page Assistant view too.
 */
export default function ChatWidget() {
  const { messages, sendMessage, isLoading } = useChatContext();
  const [expanded, setExpanded] = useState(true);
  const [draft, setDraft] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    if (!draft.trim() || isLoading) return;
    sendMessage(draft);
    setDraft("");
  }

  return (
    <div className="flex h-full min-h-[420px] flex-col rounded-xl border border-white/5 bg-slate-900/60 shadow-lg shadow-black/20">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center justify-between border-b border-white/5 px-4 py-3"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-100">
          <MessageCircle className="h-4 w-4 text-sky-400" />
          Assistant
        </span>
        {expanded && <X className="h-4 w-4 text-slate-500" />}
      </button>

      {expanded && (
        <>
          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
            {messages.length === 0 && (
              <p className="text-sm text-slate-500">
                Ask about recent alerts — e.g. &ldquo;what&apos;s happened with alice recently?&rdquo;
              </p>
            )}
            {messages.map((m) => (
              <ChatBubble key={m.id} message={m} />
            ))}
            {isLoading && (
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <Bot className="h-3.5 w-3.5" />
                Thinking...
              </div>
            )}
          </div>

          <form onSubmit={handleSubmit} className="flex items-center gap-2 border-t border-white/5 p-3">
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask the assistant..."
              className="min-w-0 flex-1 rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={isLoading || !draft.trim()}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-sky-600 text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </>
      )}
    </div>
  );
}
