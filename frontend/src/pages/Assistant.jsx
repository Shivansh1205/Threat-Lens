import { useEffect, useRef, useState } from "react";
import { Bot, Send, User as UserIcon } from "lucide-react";
import PageLayout from "../components/PageLayout/PageLayout";
import { useChatContext } from "../context/ChatContext";

// Same bubble styling/logic as ChatWidget's ChatBubble — duplicated rather
// than imported since ChatWidget doesn't export it separately, and this
// version doesn't need the collapse/expand chrome around it. Keep in sync
// with components/ChatWidget/ChatWidget.jsx if that styling changes.
function ChatBubble({ message }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`flex max-w-[70%] items-start gap-2 ${isUser ? "flex-row-reverse" : ""}`}>
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
 * Full-page Assistant view — same POST /api/v1/chat backend as the
 * Dashboard's compact ChatWidget, just with the whole page to itself.
 * Reads/writes the SAME conversation as ChatWidget via `useChatContext()`
 * (see context/ChatContext.jsx): sending a message here and switching to
 * Dashboard shows it in the widget too, and vice versa — there is exactly
 * one `useChat()` instance for the whole app, owned by `ChatProvider` in
 * App.jsx, not one per component.
 */
export default function Assistant() {
  const { messages, sendMessage, isLoading } = useChatContext();
  const [draft, setDraft] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  function handleSubmit(e) {
    e.preventDefault();
    if (!draft.trim() || isLoading) return;
    sendMessage(draft);
    setDraft("");
  }

  return (
    <PageLayout title="Assistant" subtitle="Ask about recent alerts, users, or overall threat activity">
      <div className="flex h-[calc(100vh-140px)] flex-col rounded-xl border border-white/5 bg-slate-900/60">
        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
          {messages.length === 0 && (
            <p className="text-sm text-slate-500">
              Ask about recent alerts — e.g. &ldquo;what&apos;s happened with alice recently?&rdquo; Conversation
              stays in sync with the widget on the Dashboard.
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
          <div ref={bottomRef} />
        </div>

        <form onSubmit={handleSubmit} className="flex items-center gap-2 border-t border-white/5 p-4">
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask the assistant..."
            className="min-w-0 flex-1 rounded-lg border border-white/10 bg-slate-950 px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={isLoading || !draft.trim()}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-sky-600 text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Send className="h-4 w-4" />
          </button>
        </form>
      </div>
    </PageLayout>
  );
}
