import { useCallback, useEffect, useRef, useState } from "react";
import { sendLogEvent } from "./lib/logClient";
import TestPanel from "./pages/TestPanel";

const INITIAL_PRODUCTS = [
  { id: 101, name: "Wireless Noise-Canceling Headphones", price: "$199.99", category: "Electronics" },
  { id: 102, name: "Ergonomic Mechanical Keyboard", price: "$129.50", category: "Peripherals" },
  { id: 103, name: "Ultra-Wide 4K Gaming Monitor", price: "$499.00", category: "Displays" },
  { id: 104, name: "Smart Fitness Watch v2", price: "$149.95", category: "Wearables" },
  { id: 105, name: "Portable USB-C SSD Drive 2TB", price: "$179.00", category: "Storage" },
];

export default function App() {
  const [activeTab, setActiveTab] = useState("storefront");
  
  // Real dynamic user identity state with localStorage persistence
  const [activeUser, setActiveUser] = useState(() => {
    return localStorage.getItem("shopsphere_active_user") || "harshitha";
  });
  const [customUserInput, setCustomUserInput] = useState("");
  const [activeIp] = useState("192.168.1.100");

  const [isAutoTraffic, setIsAutoTraffic] = useState(false);
  const [trafficPace, setTrafficPace] = useState("normal"); // normal (2-4s), relaxed (4-8s), fast (1-2s)
  const [telemetryLogs, setTelemetryLogs] = useState([]);
  const [totalSentCount, setTotalSentCount] = useState(0);

  // Authentication portal state
  const [authUsername, setAuthUsername] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authMessage, setAuthMessage] = useState(null);

  // Search & Checkout state
  const [searchQuery, setSearchQuery] = useState("");
  const [cartItems, setCartItems] = useState([]);
  const [actionNotice, setActionNotice] = useState(null);

  const logsEndRef = useRef(null);

  // Save active user to localStorage
  useEffect(() => {
    if (activeUser) {
      localStorage.setItem("shopsphere_active_user", activeUser);
    }
  }, [activeUser]);

  const addTelemetryLog = useCallback((entry) => {
    setTelemetryLogs((prev) => [...prev.slice(-99), entry]);
    setTotalSentCount((c) => c + 1);
  }, []);

  const dispatchEvent = useCallback(async (params) => {
    const payload = {
      userId: params.userId || activeUser,
      eventType: params.eventType,
      status: params.status || "ok",
      endpoint: params.endpoint,
      userAgent: params.userAgent || navigator.userAgent,
      port: params.port,
      country: params.country,
      ip: params.ip || activeIp,
      timestamp: params.timestamp || new Date().toISOString(),
    };

    const success = await sendLogEvent(payload);
    addTelemetryLog({
      time: new Date().toLocaleTimeString(),
      userId: payload.userId,
      eventType: payload.eventType,
      status: payload.status,
      endpoint: payload.endpoint || "-",
      ip: payload.ip,
      success,
    });
    return success;
  }, [activeIp, activeUser, addTelemetryLog]);

  // Switch or register a dynamic user identity
  const handleRegisterUser = (e) => {
    e.preventDefault();
    const u = customUserInput.trim();
    if (!u) return;
    setActiveUser(u);
    setCustomUserInput("");
    setActionNotice(`Active session updated to user: ${u}`);
    // Log login success for newly registered user
    dispatchEvent({
      userId: u,
      eventType: "LOGIN_SUCCESS",
      status: "ok",
      endpoint: "/account/register",
    });
  };

  // Controlled Dynamic Background Traffic Mode (Realistic variable timing)
  useEffect(() => {
    if (!isAutoTraffic) return;

    let timerId = null;

    const scheduleNext = () => {
      let minMs = 2000;
      let maxMs = 4500;
      if (trafficPace === "fast") {
        minMs = 1000;
        maxMs = 2200;
      } else if (trafficPace === "relaxed") {
        minMs = 4000;
        maxMs = 8500;
      }

      const delay = Math.floor(minMs + Math.random() * (maxMs - minMs));

      timerId = setTimeout(async () => {
        // Pool of dynamic test identities
        const pool = [activeUser, "user_alpha", "user_beta", "evaluator_1"];
        const randUser = pool[Math.floor(Math.random() * pool.length)];

        const randRoll = Math.random();
        if (randRoll < 0.55) {
          const endpoints = [
            "/api/v1/products",
            `/api/v1/products/${Math.floor(Math.random() * 5) + 100}`,
            "/api/v1/cart",
            "/api/v1/user/profile",
            "/api/v1/orders/history",
          ];
          const ep = endpoints[Math.floor(Math.random() * endpoints.length)];
          await dispatchEvent({ userId: randUser, eventType: "API_CALL", status: "200 OK", endpoint: ep });
        } else if (randRoll < 0.80) {
          const pages = ["/catalog", "/cart", "/dashboard", "/checkout"];
          const page = pages[Math.floor(Math.random() * pages.length)];
          await dispatchEvent({ userId: randUser, eventType: "API_CALL", status: "200 OK", endpoint: page });
        } else if (randRoll < 0.95) {
          await dispatchEvent({ userId: randUser, eventType: "LOGIN_SUCCESS", status: "ok", endpoint: "/login" });
        } else {
          // Isolated typo failure (1 attempt max) -> zero false positive alerts
          await dispatchEvent({ userId: randUser, eventType: "LOGIN_FAILURE", status: "bad_password", endpoint: "/login" });
        }

        if (isAutoTraffic) {
          scheduleNext();
        }
      }, delay);
    };

    scheduleNext();

    return () => {
      if (timerId) clearTimeout(timerId);
    };
  }, [isAutoTraffic, trafficPace, activeUser, dispatchEvent]);

  // Handle Manual Auth Portal Login
  const handleAuthSubmit = async (e) => {
    e.preventDefault();
    const u = authUsername.trim();
    if (!u) return;

    // Simulate simple auth rule: passwords length >= 6 succeed
    const isValid = authPassword.length >= 6;

    await dispatchEvent({
      userId: u,
      eventType: isValid ? "LOGIN_SUCCESS" : "LOGIN_FAILURE",
      status: isValid ? "ok" : "bad_password",
      endpoint: "/login",
    });

    if (isValid) {
      setActiveUser(u);
      setAuthMessage({ type: "success", text: `Authenticated successfully as ${u}!` });
    } else {
      setAuthMessage({ type: "error", text: `Authentication failed for ${u} (Password too short for demo)` });
    }
  };

  const handleAuthLogout = async () => {
    await dispatchEvent({
      userId: activeUser,
      eventType: "LOGOUT",
      status: "ok",
      endpoint: "/logout",
    });
    setAuthMessage({ type: "info", text: `Logged out active user ${activeUser}` });
  };

  const handleProductAction = async (product, actionName) => {
    if (actionName === "add-to-cart") {
      setCartItems((prev) => [...prev, product]);
      setActionNotice(`Added "${product.name}" to cart!`);
    }
    await dispatchEvent({
      userId: activeUser,
      eventType: "API_CALL",
      status: "200 OK",
      endpoint: `/api/v1/products/${product.id}/${actionName}`,
    });
  };

  const handleCheckout = async () => {
    if (cartItems.length === 0) return;
    await dispatchEvent({
      userId: activeUser,
      eventType: "API_CALL",
      status: "200 OK",
      endpoint: "/api/v1/checkout",
    });
    setActionNotice(`Successfully completed order for ${cartItems.length} items!`);
    setCartItems([]);
  };

  const handleSearchSubmit = async (e) => {
    e.preventDefault();
    if (!searchQuery) return;
    await dispatchEvent({
      userId: activeUser,
      eventType: "API_CALL",
      status: "200 OK",
      endpoint: `/api/v1/search?q=${encodeURIComponent(searchQuery)}`,
    });
    setActionNotice(`Searched store catalog for "${searchQuery}"`);
  };

  return (
    <div style={styles.appContainer}>
      {/* Header Banner & Telemetry Controller */}
      <header style={styles.header}>
        <div style={styles.headerTitleGroup}>
          <div style={styles.appBadge}>Real-Time Telemetry Application</div>
          <h1 style={styles.appTitle}>ShopSphere Portal</h1>
          <p style={styles.appSubtitle}>
            Realistic External E-Commerce Application streaming live security telemetry to ThreatLens
          </p>
        </div>

        {/* Telemetry Control Panel */}
        <div style={styles.telemetryBox}>
          <div style={styles.telemetryBoxRow}>
            <div style={styles.telemetryStatusGroup}>
              <span style={{ ...styles.statusDot, background: isAutoTraffic ? "#10b981" : "#f59e0b" }} />
              <strong style={{ color: "#fff", fontSize: 13 }}>
                {isAutoTraffic ? "Dynamic Traffic Generator Active" : "Manual User Mode"}
              </strong>
            </div>

            <div style={styles.counterBadge}>
              Events Sent: <span style={styles.counterNum}>{totalSentCount}</span>
            </div>
          </div>

          <div style={{ ...styles.telemetryBoxRow, marginTop: 10 }}>
            <label style={styles.toggleLabel}>
              <input
                type="checkbox"
                checked={isAutoTraffic}
                onChange={(e) => setIsAutoTraffic(e.target.checked)}
                style={{ marginRight: 8, cursor: "pointer" }}
              />
              <strong>Auto Traffic Mode</strong>
            </label>

            {isAutoTraffic && (
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ color: "#9ca3af", fontSize: 12 }}>Speed:</span>
                <select
                  value={trafficPace}
                  onChange={(e) => setTrafficPace(e.target.value)}
                  style={styles.selectInput}
                >
                  <option value="normal">Normal (2.0s - 4.5s)</option>
                  <option value="relaxed">Relaxed (4.0s - 8.5s)</option>
                  <option value="fast">Fast (1.0s - 2.2s)</option>
                </select>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Dynamic Account Registration & User Switcher Bar */}
      <div style={styles.accountBar}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ color: "#9ca3af", fontSize: 13 }}>Active Account Identity:</span>
          <span style={styles.activeUserBadge}>👤 {activeUser}</span>
          <span style={{ color: "#64748b", fontSize: 12 }}>IP: {activeIp}</span>
        </div>

        <form onSubmit={handleRegisterUser} style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            type="text"
            placeholder="Create / Switch Account Name..."
            value={customUserInput}
            onChange={(e) => setCustomUserInput(e.target.value)}
            style={styles.textInputSmall}
          />
          <button type="submit" style={styles.actionBtnPrimary}>
            Switch Account
          </button>
        </form>
      </div>

      {actionNotice && (
        <div style={styles.noticeBar}>
          ℹ️ {actionNotice}
          <button onClick={() => setActionNotice(null)} style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", float: "right" }}>✕</button>
        </div>
      )}

      {/* Navigation Tabs */}
      <nav style={styles.navTabs}>
        <button
          onClick={() => {
            setActiveTab("storefront");
            dispatchEvent({ userId: activeUser, eventType: "API_CALL", status: "200 OK", endpoint: "/catalog" });
          }}
          style={{ ...styles.navTab, borderBottomColor: activeTab === "storefront" ? "#3b82f6" : "transparent" }}
        >
          🛍️ E-Commerce Storefront
        </button>
        <button
          onClick={() => {
            setActiveTab("auth");
            dispatchEvent({ userId: activeUser, eventType: "API_CALL", status: "200 OK", endpoint: "/account" });
          }}
          style={{ ...styles.navTab, borderBottomColor: activeTab === "auth" ? "#3b82f6" : "transparent" }}
        >
          🔑 Authentication Portal
        </button>
        <button
          onClick={() => setActiveTab("testpanel")}
          style={{ ...styles.navTab, borderBottomColor: activeTab === "testpanel" ? "#3b82f6" : "transparent" }}
        >
          ⚡ Attack Scenario Trigger Panel
        </button>
        <button
          onClick={() => setActiveTab("audit")}
          style={{ ...styles.navTab, borderBottomColor: activeTab === "audit" ? "#3b82f6" : "transparent" }}
        >
          📜 Telemetry Audit Stream ({telemetryLogs.length})
        </button>
      </nav>

      {/* Main Content Area */}
      <main style={styles.mainContent}>
        {/* Tab 1: Storefront */}
        {activeTab === "storefront" && (
          <div style={styles.tabSection}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20, flexWrap: "wrap", gap: 12 }}>
              <div>
                <h2 style={styles.sectionHeading}>ShopSphere Product Catalog</h2>
                <p style={{ color: "#9ca3af", fontSize: 14 }}>
                  All actions generate live telemetry under active user <strong style={{ color: "#60a5fa" }}>{activeUser}</strong>.
                </p>
              </div>

              <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                <form onSubmit={handleSearchSubmit} style={{ display: "flex", gap: 8 }}>
                  <input
                    type="text"
                    placeholder="Search products..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    style={styles.textInput}
                  />
                  <button type="submit" style={styles.actionBtnPrimary}>
                    Search
                  </button>
                </form>

                {cartItems.length > 0 && (
                  <button onClick={handleCheckout} style={styles.btnSuccess}>
                    Checkout ({cartItems.length} items)
                  </button>
                )}
              </div>
            </div>

            <div style={styles.productGrid}>
              {INITIAL_PRODUCTS.map((prod) => (
                <div key={prod.id} style={styles.productCard}>
                  <div style={styles.productBadge}>{prod.category}</div>
                  <h3 style={styles.productTitle}>{prod.name}</h3>
                  <div style={styles.productPrice}>{prod.price}</div>
                  <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
                    <button
                      onClick={() => handleProductAction(prod, "view")}
                      style={styles.actionBtnSecondary}
                    >
                      View
                    </button>
                    <button
                      onClick={() => handleProductAction(prod, "add-to-cart")}
                      style={styles.actionBtnPrimary}
                    >
                      Add to Cart
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 2: Authentication Portal */}
        {activeTab === "auth" && (
          <div style={styles.tabSection}>
            <h2 style={styles.sectionHeading}>User Authentication Portal</h2>
            <p style={{ color: "#9ca3af", fontSize: 14, marginBottom: 20 }}>
              Simulates authentication for any demo account. Generates <code style={styles.inlineCode}>LOGIN_SUCCESS</code> or <code style={styles.inlineCode}>LOGIN_FAILURE</code> telemetry.
            </p>

            <div style={styles.authContainer}>
              <div style={styles.authCard}>
                <h3>Account Sign In</h3>
                <form onSubmit={handleAuthSubmit}>
                  <div style={{ marginBottom: 14 }}>
                    <label style={styles.fieldLabel}>Username</label>
                    <input
                      type="text"
                      value={authUsername}
                      onChange={(e) => setAuthUsername(e.target.value)}
                      placeholder="e.g. harshitha, teammate1, evaluator1..."
                      style={styles.textInputFull}
                    />
                  </div>
                  <div style={{ marginBottom: 14 }}>
                    <label style={styles.fieldLabel}>Password</label>
                    <input
                      type="password"
                      value={authPassword}
                      onChange={(e) => setAuthPassword(e.target.value)}
                      placeholder="Enter password (6+ chars succeeds, shorter fails)..."
                      style={styles.textInputFull}
                    />
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button type="submit" style={styles.actionBtnPrimary}>
                      Sign In
                    </button>
                    <button type="button" onClick={handleAuthLogout} style={styles.actionBtnDanger}>
                      Sign Out ({activeUser})
                    </button>
                  </div>
                </form>

                {authMessage && (
                  <div
                    style={{
                      marginTop: 16,
                      padding: 10,
                      borderRadius: 6,
                      fontSize: 14,
                      background: authMessage.type === "success" ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)",
                      color: authMessage.type === "success" ? "#34d399" : "#f87171",
                      border: `1px solid ${authMessage.type === "success" ? "#059669" : "#dc2626"}`,
                    }}
                  >
                    {authMessage.text}
                  </div>
                )}
              </div>

              <div style={styles.authInfoCard}>
                <h4>Live Telemetry Notes:</h4>
                <p style={{ color: "#d1d5db", fontSize: 13, lineHeight: 1.6 }}>
                  - Any person can create their own temporary demo account without pre-configuration.
                </p>
                <p style={{ color: "#d1d5db", fontSize: 13, lineHeight: 1.6, marginTop: 8 }}>
                  - Authentic actions update the user's persistent <code style={styles.inlineCode}>BehaviorProfile</code> on the backend.
                </p>
                <p style={{ color: "#9ca3af", fontSize: 12, marginTop: 12 }}>
                  Submitting failed password attempts will immediately stream <code style={styles.inlineCode}>LOGIN_FAILURE</code> logs to ThreatLens.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Security Attack Scenario Trigger Panel */}
        {activeTab === "testpanel" && (
          <div style={styles.tabSection}>
            <TestPanel currentUser={activeUser} currentIp={activeIp} />
          </div>
        )}

        {/* Tab 4: Audit Stream */}
        {activeTab === "audit" && (
          <div style={styles.tabSection}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <h2 style={styles.sectionHeading}>Live Client Telemetry Audit</h2>
              <button onClick={() => setTelemetryLogs([])} style={styles.actionBtnSecondary}>
                Clear Logs
              </button>
            </div>
            <div style={styles.logTerminal}>
              {telemetryLogs.length === 0 ? (
                <div style={{ color: "#6b7280", fontStyle: "italic" }}>No telemetry logs recorded yet in this session.</div>
              ) : (
                telemetryLogs.map((log, index) => (
                  <div key={index} style={{ marginBottom: 4, display: "flex", gap: 12 }}>
                    <span style={{ color: "#6b7280" }}>[{log.time}]</span>
                    <span style={{ color: "#38bdf8", width: 110 }}>{log.userId}</span>
                    <span style={{ color: "#facc15", width: 120 }}>{log.eventType}</span>
                    <span style={{ color: "#a7f3d0", width: 80 }}>{log.status}</span>
                    <span style={{ color: "#94a3b8", flexGrow: 1 }}>{log.endpoint}</span>
                    <span style={{ color: log.success ? "#4ade80" : "#f87171" }}>
                      {log.success ? "HTTP 201" : "FAILED"}
                    </span>
                  </div>
                ))
              )}
              <div ref={logsEndRef} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

const styles = {
  appContainer: {
    maxWidth: "1100px",
    margin: "0 auto",
    padding: "24px 16px",
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
    color: "#f3f4f6",
    backgroundColor: "#0f172a",
    minHeight: "100vh",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 16,
    paddingBottom: 20,
    borderBottom: "1px solid #1e293b",
  },
  headerTitleGroup: {
    textAlign: "left",
  },
  appBadge: {
    display: "inline-block",
    backgroundColor: "#1e1b4b",
    color: "#818cf8",
    fontSize: "12px",
    fontWeight: "600",
    padding: "3px 10px",
    borderRadius: "12px",
    marginBottom: "6px",
    border: "1px solid #3730a3",
  },
  appTitle: {
    margin: 0,
    fontSize: "28px",
    fontWeight: "700",
    color: "#f9fafb",
  },
  appSubtitle: {
    margin: "4px 0 0",
    fontSize: "14px",
    color: "#9ca3af",
  },
  telemetryBox: {
    backgroundColor: "#1e293b",
    border: "1px solid #334155",
    borderRadius: "8px",
    padding: "12px 16px",
    minWidth: "320px",
  },
  telemetryBoxRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  telemetryStatusGroup: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: "50%",
    display: "inline-block",
  },
  counterBadge: {
    backgroundColor: "#0f172a",
    padding: "4px 8px",
    borderRadius: "4px",
    fontSize: "12px",
    color: "#cbd5e1",
    border: "1px solid #334155",
  },
  counterNum: {
    color: "#38bdf8",
    fontWeight: "700",
  },
  toggleLabel: {
    display: "flex",
    alignItems: "center",
    fontSize: "13px",
    color: "#e2e8f0",
    cursor: "pointer",
  },
  selectInput: {
    backgroundColor: "#0f172a",
    color: "#e2e8f0",
    border: "1px solid #475569",
    borderRadius: "4px",
    padding: "3px 8px",
    fontSize: "12px",
  },
  accountBar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 12,
    backgroundColor: "#1e293b",
    padding: "10px 16px",
    borderRadius: "6px",
    margin: "16px 0 10px",
    border: "1px solid #334155",
  },
  activeUserBadge: {
    backgroundColor: "#2563eb",
    color: "#fff",
    fontWeight: "600",
    padding: "3px 10px",
    borderRadius: "4px",
    fontSize: "13px",
  },
  noticeBar: {
    backgroundColor: "rgba(59, 130, 246, 0.15)",
    border: "1px solid #3b82f6",
    color: "#93c5fd",
    padding: "8px 14px",
    borderRadius: "6px",
    fontSize: "13px",
    marginBottom: "16px",
  },
  navTabs: {
    display: "flex",
    gap: 12,
    borderBottom: "1px solid #334155",
    marginBottom: 20,
    overflowX: "auto",
  },
  navTab: {
    backgroundColor: "transparent",
    color: "#e2e8f0",
    border: "none",
    borderBottomWidth: "3px",
    borderBottomStyle: "solid",
    padding: "10px 16px",
    fontSize: "14px",
    fontWeight: "600",
    cursor: "pointer",
  },
  mainContent: {
    textAlign: "left",
  },
  tabSection: {
    backgroundColor: "#1e293b",
    borderRadius: "8px",
    padding: "24px",
    border: "1px solid #334155",
  },
  sectionHeading: {
    margin: 0,
    fontSize: "20px",
    color: "#f3f4f6",
  },
  inlineCode: {
    backgroundColor: "#0f172a",
    color: "#38bdf8",
    padding: "2px 6px",
    borderRadius: "4px",
    fontSize: "13px",
    fontFamily: "monospace",
  },
  productGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
    gap: 16,
    marginTop: 16,
  },
  productCard: {
    backgroundColor: "#0f172a",
    border: "1px solid #334155",
    borderRadius: "8px",
    padding: "16px",
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between",
  },
  productBadge: {
    fontSize: "11px",
    color: "#818cf8",
    fontWeight: "600",
    textTransform: "uppercase",
  },
  productTitle: {
    margin: "8px 0",
    fontSize: "15px",
    fontWeight: "600",
    color: "#f9fafb",
  },
  productPrice: {
    fontSize: "16px",
    fontWeight: "700",
    color: "#34d399",
  },
  btnSuccess: {
    backgroundColor: "#059669",
    color: "#fff",
    border: "none",
    borderRadius: "4px",
    padding: "6px 12px",
    fontSize: "13px",
    fontWeight: "600",
    cursor: "pointer",
  },
  actionBtnPrimary: {
    backgroundColor: "#2563eb",
    color: "#fff",
    border: "none",
    borderRadius: "4px",
    padding: "6px 12px",
    fontSize: "13px",
    fontWeight: "600",
    cursor: "pointer",
  },
  actionBtnSecondary: {
    backgroundColor: "#334155",
    color: "#e2e8f0",
    border: "none",
    borderRadius: "4px",
    padding: "6px 12px",
    fontSize: "13px",
    cursor: "pointer",
  },
  actionBtnDanger: {
    backgroundColor: "#dc2626",
    color: "#fff",
    border: "none",
    borderRadius: "4px",
    padding: "6px 12px",
    fontSize: "13px",
    fontWeight: "600",
    cursor: "pointer",
  },
  textInput: {
    backgroundColor: "#0f172a",
    border: "1px solid #475569",
    color: "#fff",
    padding: "6px 12px",
    borderRadius: "4px",
    fontSize: "13px",
  },
  textInputSmall: {
    backgroundColor: "#0f172a",
    border: "1px solid #475569",
    color: "#fff",
    padding: "4px 8px",
    borderRadius: "4px",
    fontSize: "12px",
    width: "180px",
  },
  textInputFull: {
    width: "100%",
    backgroundColor: "#0f172a",
    border: "1px solid #475569",
    color: "#fff",
    padding: "8px 12px",
    borderRadius: "4px",
    fontSize: "14px",
    boxSizing: "border-box",
  },
  fieldLabel: {
    display: "block",
    fontSize: "13px",
    color: "#cbd5e1",
    marginBottom: "4px",
  },
  authContainer: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 24,
  },
  authCard: {
    backgroundColor: "#0f172a",
    border: "1px solid #334155",
    borderRadius: "8px",
    padding: "20px",
  },
  authInfoCard: {
    backgroundColor: "#0f172a",
    border: "1px solid #334155",
    borderRadius: "8px",
    padding: "20px",
  },
  logTerminal: {
    backgroundColor: "#090d16",
    border: "1px solid #1e293b",
    borderRadius: "6px",
    padding: "12px",
    height: "320px",
    overflowY: "auto",
    fontFamily: "Consolas, Monaco, monospace",
    fontSize: "12px",
  },
};
