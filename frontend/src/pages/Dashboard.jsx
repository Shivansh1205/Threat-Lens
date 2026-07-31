import AlertList from "../components/AlertList/AlertList";
import { useAlerts } from "../hooks/useAlerts";

export default function Dashboard() {
  const { alerts, error } = useAlerts();

  return (
    <div className="min-h-screen bg-gray-950 p-6 text-gray-100">
      <h1 className="mb-4 text-2xl font-bold">ThreatLens</h1>
      {error && (
        <p className="mb-4 text-red-400">Could not load alerts: {error}</p>
      )}
      <AlertList alerts={alerts} />
    </div>
  );
}
