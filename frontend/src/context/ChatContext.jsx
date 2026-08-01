import { createContext, useContext } from "react";
import { useChat } from "../hooks/useChat";

const ChatContext = createContext(null);

/**
 * Lifts `useChat`'s state (session_id, messages, sendMessage, isLoading,
 * error) up to a single shared instance, so the compact Dashboard
 * `ChatWidget` and the full-page `Assistant` view read/write the SAME
 * conversation rather than each owning an independent one.
 *
 * Before this, `ChatWidget` called `useChat()` directly — fine as long as
 * only one component ever needed chat state, but the moment a second
 * consumer (the Assistant page) also called `useChat()`, it would get its
 * own separate `session_id` and `messages` array, completely disconnected
 * from whatever was already on screen. Navigating Dashboard -> Assistant
 * -> Dashboard would silently reset the conversation, and a message sent on
 * one view would never appear on the other.
 *
 * `ChatProvider` wraps the app once (see App.jsx) and calls `useChat()`
 * exactly once; both `ChatWidget` and `Assistant` consume the same value via
 * `useChatContext()` below instead of calling the hook themselves. Still
 * in-memory only (no localStorage) — a full page reload still starts a
 * fresh session, same as before; this only fixes state loss from
 * client-side navigation between pages within one session.
 */
export function ChatProvider({ children }) {
  const chat = useChat();
  return <ChatContext.Provider value={chat}>{children}</ChatContext.Provider>;
}

export function useChatContext() {
  const ctx = useContext(ChatContext);
  if (ctx === null) {
    throw new Error("useChatContext must be used within a <ChatProvider>");
  }
  return ctx;
}
