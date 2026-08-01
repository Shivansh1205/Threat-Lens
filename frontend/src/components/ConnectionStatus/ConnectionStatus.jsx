const STATUS_CONFIG = {
  connected: { label: "System Live", dot: "bg-emerald-400", text: "text-emerald-300" },
  connecting: { label: "Connecting...", dot: "bg-amber-400 animate-pulse", text: "text-amber-300" },
  reconnecting: { label: "Reconnecting...", dot: "bg-amber-400 animate-pulse", text: "text-amber-300" },
  disconnected: { label: "Disconnected", dot: "bg-red-400", text: "text-red-300" },
};

/** Small "System Secure"-style badge reflecting useAlertStream's connectionStatus. */
export default function ConnectionStatus({ status }) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.disconnected;

  return (
    <span className="flex items-center gap-2 rounded-full border border-white/10 bg-slate-900/60 px-3 py-1.5 text-xs font-medium">
      <span className={`h-2 w-2 rounded-full ${config.dot}`} />
      <span className={config.text}>{config.label}</span>
    </span>
  );
}
