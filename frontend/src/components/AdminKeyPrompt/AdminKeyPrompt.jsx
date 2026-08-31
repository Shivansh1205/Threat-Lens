import { useState } from "react";

export default function AdminKeyPrompt({ onUnlock, error }) {
  const [draft, setDraft] = useState("");
  return (
    <div className="rounded-lg border border-amber-500/20 bg-amber-950/20 p-3 text-xs text-amber-200">
      <p className="font-medium">Administrator authorization required</p>
      <p className="mt-1 text-amber-300/80">Enter the admin API key to request user analysis from Groq.</p>
      <form className="mt-3 flex gap-2" onSubmit={(event) => { event.preventDefault(); onUnlock(draft); }}>
        <input
          type="password"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Admin API key"
          className="min-w-0 flex-1 rounded border border-white/10 bg-slate-950 px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-sky-500"
        />
        <button type="submit" disabled={!draft.trim()} className="rounded bg-sky-600 px-3 py-1.5 font-medium text-white disabled:opacity-40">Unlock</button>
      </form>
      {error && <p className="mt-2 text-red-300">{error}</p>}
    </div>
  );
}
