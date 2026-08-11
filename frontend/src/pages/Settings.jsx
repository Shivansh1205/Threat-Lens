import { Check, Moon, Sun } from "lucide-react";
import PageLayout from "../components/PageLayout/PageLayout";
import { useTheme } from "../context/ThemeContext";
import DetectionSettings from "../components/DetectionSettings/DetectionSettings";

const OPTIONS = [
  { value: "light", label: "Light", description: "Bright surfaces for daytime analysis.", icon: Sun },
  { value: "dark", label: "Dark", description: "Reduced glare for low-light monitoring.", icon: Moon },
];

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  return (
    <PageLayout title="Settings" subtitle="Personalize your ThreatLens workspace">
      <section className="max-w-3xl rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/5 dark:bg-slate-900/40">
        <h2 className="font-semibold text-slate-900 dark:text-slate-100">Appearance</h2>
        <p className="mt-1 text-sm text-slate-500">Your selection is saved in this browser.</p>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          {OPTIONS.map(({ value, label, description, icon: Icon }) => {
            const selected = theme === value;
            return (
              <button key={value} type="button" onClick={() => setTheme(value)} aria-pressed={selected} className={`relative rounded-xl border p-5 text-left transition ${selected ? "border-sky-500 bg-sky-50 ring-2 ring-sky-500/20 dark:bg-sky-500/10" : "border-slate-200 hover:border-slate-300 dark:border-white/10 dark:hover:border-white/20"}`}>
                {selected && <Check className="absolute right-4 top-4 h-4 w-4 text-sky-600 dark:text-sky-300" />}
                <Icon className="h-6 w-6 text-sky-600 dark:text-sky-400" />
                <p className="mt-3 font-semibold">{label}</p>
                <p className="mt-1 text-sm text-slate-500">{description}</p>
              </button>
            );
          })}
        </div>
      </section>
      <DetectionSettings />
    </PageLayout>
  );
}
