import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ChatProvider } from "./context/ChatContext";
import Alerts from "./pages/Alerts";
import Assistant from "./pages/Assistant";
import Dashboard from "./pages/Dashboard";
import UserAnalytics from "./pages/UserAnalytics";

/**
 * Client-side routing via react-router-dom (added this phase — confirmed
 * with the user before adding, since it wasn't previously a dependency).
 * `ChatProvider` wraps everything above the routes so Dashboard's
 * `ChatWidget` and the full-page `Assistant` view share one conversation
 * (see context/ChatContext.jsx) regardless of which route is active.
 *
 * Threat Feed / Reports / Settings have no route yet — the Sidebar keeps
 * them as visually-disabled placeholders rather than linking to a page
 * that doesn't exist.
 */
export default function App() {
  return (
    <ChatProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/users" element={<UserAnalytics />} />
          <Route path="/assistant" element={<Assistant />} />
        </Routes>
      </BrowserRouter>
    </ChatProvider>
  );
}
