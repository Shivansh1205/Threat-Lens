import { KeyRound, Loader2, LogOut, RotateCcw, Save, ShieldCheck, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  ADMIN_KEY_STORAGE,
  cloneSettings,
  DETECTOR_GROUPS,
  validateDetectionSettings,
} from "../../utils/detectionSettings";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8002";

async function settingsRequest(key, options = {}) {
  const response = await fetch(`${API_URL}/api/v1/admin/detection-settings`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-ThreatLens-Admin-Key": key,
      ...options.headers,
    },
  });
  if (response.status === 401) {
    const error = new Error("The admin API key is invalid.");
    error.unauthorized = true;
    throw error;
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail?.[0]?.msg || body?.detail || `Request failed (HTTP ${response.status})`);
  }
  return response.json();
}

function LimitField({ groupKey, field, label, unit, value, defaultValue, error, onChange }) {
  return (
    <label className="text-xs font-medium text-slate-500">
      <span className="mb-1 block">{label}</span>
      <div className="relative">
        <input
          type="number"
          min="1"
          max={field === "window_seconds" ? 3600 : 100000}
          step="1"
          value={value}
          onChange={(event) => onChange(groupKey, field, event.target.value)}
          aria-invalid={Boolean(error)}
          className={`w-full rounded-lg border bg-white px-3 py-2 pr-20 text-sm text-slate-900 outline-none focus:border-sky-500 dark:bg-slate-950 dark:text-slate-100 ${error ? "border-red-400" : "border-slate-200 dark:border-white/10"}`}
        />
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[11px] text-slate-400">{unit}</span>
      </div>
      <span className="mt-1 block text-[11px] text-slate-400">Default: {defaultValue}</span>
      {error && <span className="mt-1 block text-[11px] text-red-600 dark:text-red-300">{error}</span>}
    </label>
  );
}

export default function DetectionSettings() {
  const [adminKey, setAdminKey] = useState(() => sessionStorage.getItem(ADMIN_KEY_STORAGE) || "");
  const [keyDraft, setKeyDraft] = useState("");
  const [data, setData] = useState(null);
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(Boolean(adminKey));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const errors = useMemo(() => draft ? validateDetectionSettings(draft) : {}, [draft]);
  const dirty = Boolean(data && draft && JSON.stringify(data.values) !== JSON.stringify(draft));

  function lock(message = null) {
    sessionStorage.removeItem(ADMIN_KEY_STORAGE);
    setAdminKey("");
    setData(null);
    setDraft(null);
    setLoading(false);
    setError(message);
  }

  async function load(key) {
    setLoading(true);
    setError(null);
    try {
      const response = await settingsRequest(key);
      sessionStorage.setItem(ADMIN_KEY_STORAGE, key);
      setAdminKey(key);
      setData(response);
      setDraft(cloneSettings(response.values));
      setKeyDraft("");
    } catch (requestError) {
      if (requestError.unauthorized) lock(requestError.message);
      else setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (adminKey) load(adminKey);
    // The stored key is intentionally checked only on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function updateField(group, field, rawValue) {
    setDraft((current) => ({
      ...current,
      [group]: {
        ...current[group],
        [field]: rawValue === "" ? "" : Number(rawValue),
      },
    }));
    setNotice(null);
  }

  async function save() {
    if (!dirty || Object.keys(errors).length) return;
    setSaving(true);
    setError(null);
    try {
      const response = await settingsRequest(adminKey, {
        method: "PUT",
        body: JSON.stringify(draft),
      });
      setData(response);
      setDraft(cloneSettings(response.values));
      setNotice("Detection limits saved. Active detector windows were cleared.");
    } catch (requestError) {
      if (requestError.unauthorized) lock(requestError.message);
      else setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function resetDefaults() {
    if (!window.confirm("Restore every detection limit to its environment default? Active detector windows will be cleared.")) return;
    setSaving(true);
    setError(null);
    try {
      const response = await settingsRequest(adminKey, { method: "DELETE" });
      setData(response);
      setDraft(cloneSettings(response.values));
      setNotice("Environment defaults restored. Active detector windows were cleared.");
    } catch (requestError) {
      if (requestError.unauthorized) lock(requestError.message);
      else setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  if (!adminKey || !data) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/5 dark:bg-slate-900/40">
        <div className="flex items-start gap-3"><div className="rounded-lg bg-sky-50 p-2 text-sky-600 dark:bg-sky-500/10 dark:text-sky-300"><KeyRound className="h-5 w-5" /></div><div><h2 className="font-semibold">Detection Limits</h2><p className="mt-1 text-sm text-slate-500">Enter the admin API key to view or change global detector thresholds.</p></div></div>
        <form onSubmit={(event) => { event.preventDefault(); if (keyDraft.trim()) load(keyDraft.trim()); }} className="mt-5 flex max-w-lg gap-2">
          <input type="password" value={keyDraft} onChange={(event) => setKeyDraft(event.target.value)} placeholder="Admin API key" autoComplete="current-password" className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-sky-500 dark:border-white/10 dark:bg-slate-950" />
          <button type="submit" disabled={loading || !keyDraft.trim()} className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{loading && <Loader2 className="h-4 w-4 animate-spin" />}Unlock</button>
        </form>
        {error && <p className="mt-3 text-sm text-red-600 dark:text-red-300">{error}</p>}
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/5 dark:bg-slate-900/40">
      <div className="flex flex-wrap items-start justify-between gap-3"><div className="flex items-start gap-3"><div className="rounded-lg bg-emerald-50 p-2 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-300"><ShieldCheck className="h-5 w-5" /></div><div><h2 className="font-semibold">Detection Limits</h2><p className="mt-1 text-sm text-slate-500">Global limits are applied to real monitored events. Saving clears active sliding windows.</p></div></div><button type="button" onClick={() => lock()} className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 dark:border-white/10 dark:text-slate-300"><LogOut className="h-3.5 w-3.5" />Forget key</button></div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs"><span className={`rounded-full px-2.5 py-1 font-medium ${data.is_overridden ? "bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300" : "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"}`}>{data.is_overridden ? "Custom limits active" : "Environment defaults active"}</span>{data.updated_at && <span className="px-1 py-1 text-slate-500">Updated {new Date(data.updated_at).toLocaleString()}</span>}</div>
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        {DETECTOR_GROUPS.map((group) => <article key={group.key} className="rounded-xl border border-slate-200 p-4 dark:border-white/10"><h3 className="font-semibold">{group.title}</h3><p className="mt-1 text-xs text-slate-500">{group.description}</p><div className="mt-4 grid gap-3 sm:grid-cols-2">{group.fields.map(([field, label, unit]) => <LimitField key={field} groupKey={group.key} field={field} label={label} unit={unit} value={draft[group.key][field]} defaultValue={data.defaults[group.key][field]} error={errors[`${group.key}.${field}`]} onChange={updateField} />)}</div>{errors[`${group.key}.order`] && <p className="mt-3 flex items-center gap-1.5 text-xs text-red-600 dark:text-red-300"><TriangleAlert className="h-3.5 w-3.5" />{errors[`${group.key}.order`]}</p>}</article>)}
      </div>
      {error && <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-950/30 dark:text-red-300">{error}</p>}
      {notice && <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-950/20 dark:text-emerald-300">{notice}</p>}
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4 dark:border-white/10"><button type="button" onClick={resetDefaults} disabled={saving || !data.is_overridden} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 disabled:opacity-40 dark:border-white/10 dark:text-slate-300"><RotateCcw className="h-4 w-4" />Reset defaults</button><div className="flex gap-2"><button type="button" onClick={() => { setDraft(cloneSettings(data.values)); setNotice(null); }} disabled={!dirty || saving} className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium disabled:opacity-40 dark:border-white/10">Discard</button><button type="button" onClick={save} disabled={!dirty || saving || Object.keys(errors).length > 0} className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-40">{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}Save changes</button></div></div>
    </section>
  );
}
