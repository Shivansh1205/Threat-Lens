import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ChatProvider } from "./context/ChatContext";
import { ThemeProvider } from "./context/ThemeContext";
import Alerts from "./pages/Alerts";
import Assistant from "./pages/Assistant";
import Dashboard from "./pages/Dashboard";
import UserAnalytics from "./pages/UserAnalytics";
import Reports from "./pages/Reports";
import SettingsPage from "./pages/Settings";
import ThreatFeed from "./pages/ThreatFeed";

/**
 * ChatProvider sits above the routes so the dashboard widget and full Assistant
 * page share one conversation while the user navigates between views.
 */
export default function App() {
  return (
    <ThemeProvider>
      <ChatProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/threat-feed" element={<ThreatFeed />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/users" element={<UserAnalytics />} />
            <Route path="/assistant" element={<Assistant />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </BrowserRouter>
      </ChatProvider>
    </ThemeProvider>
  );
}
