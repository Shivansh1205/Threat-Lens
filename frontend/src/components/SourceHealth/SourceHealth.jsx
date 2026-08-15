import { Database, FileWarning, Radio, RotateCcw } from "lucide-react";
import { formatRelativeTime } from "../../utils/time";

export default function SourceHealth({ sources }) {
  if (sources.length === 0) return <p className="text-sm text-slate-500">No collector has checked in yet.</p>;
  return <div className="grid gap-3 md:grid-cols-2">{sources.map((source) => (
    <article key={source.source_id} className="rounded-lg border border-white/5 bg-slate-950/40 p-4">
      <div className="flex items-center justify-between"><div><p className="font-medium text-slate-200">{source.name}</p><p className="text-xs text-slate-500">{source.source_id} · {source.source_type}</p></div><span className={`rounded-full px-2 py-1 text-xs font-semibold ${source.status === "live" ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-300"}`}><Radio className="mr-1 inline h-3 w-3" />{source.status}</span></div>
      <div className="mt-4 grid grid-cols-3 gap-2 text-xs text-slate-400"><span><Database className="mb-1 h-4 w-4" />{source.events_received} events</span><span><FileWarning className="mb-1 h-4 w-4" />{source.malformed_lines} rejected</span><span><RotateCcw className="mb-1 h-4 w-4" />{source.delivery_failures} retries</span></div>
      <p className="mt-3 text-xs text-slate-500">Last traffic: {source.last_event_at ? formatRelativeTime(source.last_event_at) : "none yet"}</p>
    </article>
  ))}</div>;
}
