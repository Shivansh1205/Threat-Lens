import { useState } from "react";
import { sendLogEvent } from "../lib/logClient";

function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
}

export default function TestPanel({ currentUser = "demo_user", currentIp = "192.168.1.100" }) {
    const [logs, setLogs] = useState([]);
    const [running, setRunning] = useState(false);

    function log(msg) {
        setLogs((prev) => [...prev.slice(-40), msg]);
    }

    // 1. Brute Force Burst (25 failures)
    async function runBruteForce() {
        const user = currentUser;
        const ip = currentIp || "203.0.113.7";
        log(`[SCENARIO] Starting Brute Force Attack for user: ${user} from IP: ${ip}`);
        for (let i = 0; i < 25; i++) {
            await sendLogEvent({
                userId: user,
                ip,
                eventType: "LOGIN_FAILURE",
                status: "bad_password",
                endpoint: "/login",
            });
            if ((i + 1) % 5 === 0) {
                log(`brute_force: failure ${i + 1}/25 sent`);
            }
            await sleep(80);
        }
        log("✅ brute_force burst complete — check ThreatLens dashboard for MEDIUM/HIGH/CRITICAL alerts!");
    }

    // 2. Brute Force + Compromise (6 failures then 1 success)
    async function runBruteForceSuccess() {
        const user = currentUser;
        const ip = currentIp || "203.0.113.15";
        log(`[SCENARIO] Starting Brute Force + Compromise for user: ${user}`);
        for (let i = 0; i < 6; i++) {
            await sendLogEvent({
                userId: user,
                ip,
                eventType: "LOGIN_FAILURE",
                status: "bad_password",
                endpoint: "/login",
            });
            log(`brute_force_success: failure ${i + 1}/6`);
            await sleep(100);
        }
        // Send final success event
        await sendLogEvent({
            userId: user,
            ip,
            eventType: "LOGIN_SUCCESS",
            status: "ok",
            endpoint: "/login",
        });
        log("🚨 brute_force_success sent — expect CRITICAL compromise alert on ThreatLens dashboard!");
    }

    // 3. Port Scan Scenario (60 distinct ports)
    async function runPortScan() {
        const ip = currentIp || "198.51.100.42";
        const user = currentUser;
        log(`[SCENARIO] Starting Port Scan from source IP: ${ip}`);
        for (let i = 1; i <= 60; i++) {
            await sendLogEvent({
                userId: user,
                ip,
                eventType: "PORT_ACCESS",
                status: "ok",
                port: i,
            });
            if (i % 15 === 0) {
                log(`port_scan: ${i}/60 distinct ports probed`);
            }
            await sleep(25);
        }
        log("✅ port_scan complete — expect HIGH (15+) and CRITICAL (50+) alerts on ThreatLens!");
    }

    // 4. Unusual IP Scenario (3 bootstrap logins from normal IP, then 1 from new IP)
    async function runUnusualIp() {
        const user = currentUser;
        const normalIp = "10.0.0.10";
        const newIp = "10.0.0.99";

        log(`[SCENARIO] Bootstrapping known IP baseline for ${user}...`);
        for (let i = 0; i < 3; i++) {
            await sendLogEvent({
                userId: user,
                ip: normalIp,
                eventType: "LOGIN_SUCCESS",
                status: "ok",
                endpoint: "/login",
            });
            log(`unusual_ip: bootstrap login ${i + 1}/3 from ${normalIp}`);
            await sleep(150);
        }

        log(`unusual_ip: Sending login from new IP: ${newIp}`);
        await sendLogEvent({
            userId: user,
            ip: newIp,
            eventType: "LOGIN_SUCCESS",
            status: "ok",
            endpoint: "/login",
        });
        log("🚨 unusual_ip sent — expect LOW/MEDIUM alert on ThreatLens dashboard!");
    }

    // 5. User Risk Escalation (Triggers cumulative alerts to push user into High Risk User panel)
    async function runRiskEscalation() {
        const user = currentUser;
        const ip = currentIp || "192.168.1.55";
        log(`[SCENARIO] Escalating Cumulative User Risk Score for: ${user}`);
        for (let i = 0; i < 12; i++) {
            await sendLogEvent({
                userId: user,
                ip,
                eventType: "LOGIN_FAILURE",
                status: "bad_password",
                endpoint: "/login",
            });
            await sleep(50);
        }
        log(`✅ Risk escalation complete — check High-Risk Users panel on ThreatLens dashboard for ${user}!`);
    }

    // 6. Normal Traffic Burst (10 legitimate actions -> 0 alerts)
    async function runNormal() {
        const user = currentUser;
        const ip = currentIp || "192.168.1.100";
        log(`[SCENARIO] Generating 10 legitimate events for user: ${user}`);
        await sendLogEvent({ userId: user, ip, eventType: "LOGIN_SUCCESS", status: "ok", endpoint: "/login" });
        for (let i = 0; i < 8; i++) {
            await sendLogEvent({
                userId: user,
                ip,
                eventType: "API_CALL",
                status: "200 OK",
                endpoint: `/api/v1/catalog/item/${i + 1}`,
            });
            log(`normal: API call ${i + 1}/8`);
            await sleep(100);
        }
        await sendLogEvent({ userId: user, ip, eventType: "LOGOUT", status: "ok", endpoint: "/logout" });
        log("✅ normal traffic burst complete — expect 0 alerts!");
    }

    async function trigger(fn) {
        setRunning(true);
        setLogs([]);
        await fn();
        setRunning(false);
    }

    return (
        <div style={styles.container}>
            <div style={styles.headerBox}>
                <h3 style={styles.title}>⚡ Security Attack Scenario Trigger Panel</h3>
                <p style={styles.subtitle}>
                    All security scenarios execute live using your active user account:{" "}
                    <strong style={{ color: "#60a5fa" }}>{currentUser}</strong> (Source IP: {currentIp})
                </p>
            </div>

            <div style={styles.buttonGrid}>
                <button disabled={running} onClick={() => trigger(runBruteForce)} style={styles.btnDanger}>
                    🔴 Brute Force Attack (25 Failures)
                </button>
                <button disabled={running} onClick={() => trigger(runBruteForceSuccess)} style={styles.btnDanger}>
                    🚨 Brute Force + Compromise (Success)
                </button>
                <button disabled={running} onClick={() => trigger(runPortScan)} style={styles.btnWarning}>
                    🌐 Port Scan Attack (60 Ports)
                </button>
                <button disabled={running} onClick={() => trigger(runUnusualIp)} style={styles.btnWarning}>
                    🚩 Unusual IP Login Trigger
                </button>
                <button disabled={running} onClick={() => trigger(runRiskEscalation)} style={styles.btnPurple}>
                    📈 Escalate User Risk Score
                </button>
                <button disabled={running} onClick={() => trigger(runNormal)} style={styles.btnSuccess}>
                    🟢 Normal Traffic Burst (0 Alerts)
                </button>
            </div>

            <div style={styles.terminal}>
                <div style={styles.terminalHeader}>Execution Console Output</div>
                {logs.length === 0 ? (
                    <div style={{ color: "#6b7280", fontStyle: "italic" }}>
                        Select any scenario above to execute against ThreatLens.
                    </div>
                ) : (
                    logs.map((l, i) => <div key={i} style={{ marginBottom: 3 }}>{l}</div>)
                )}
            </div>
        </div>
    );
}

const styles = {
    container: {
        textAlign: "left",
    },
    headerBox: {
        marginBottom: 16,
    },
    title: {
        margin: 0,
        fontSize: "18px",
        color: "#f3f4f6",
    },
    subtitle: {
        margin: "4px 0 0",
        fontSize: "13px",
        color: "#9ca3af",
    },
    buttonGrid: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
        gap: 10,
        marginBottom: 20,
    },
    btnDanger: {
        backgroundColor: "#b91c1c",
        color: "#fff",
        border: "none",
        borderRadius: "6px",
        padding: "10px 14px",
        fontSize: "13px",
        fontWeight: "600",
        cursor: "pointer",
    },
    btnWarning: {
        backgroundColor: "#d97706",
        color: "#fff",
        border: "none",
        borderRadius: "6px",
        padding: "10px 14px",
        fontSize: "13px",
        fontWeight: "600",
        cursor: "pointer",
    },
    btnPurple: {
        backgroundColor: "#7c3aed",
        color: "#fff",
        border: "none",
        borderRadius: "6px",
        padding: "10px 14px",
        fontSize: "13px",
        fontWeight: "600",
        cursor: "pointer",
    },
    btnSuccess: {
        backgroundColor: "#059669",
        color: "#fff",
        border: "none",
        borderRadius: "6px",
        padding: "10px 14px",
        fontSize: "13px",
        fontWeight: "600",
        cursor: "pointer",
    },
    terminal: {
        backgroundColor: "#090d16",
        border: "1px solid #1e293b",
        borderRadius: "6px",
        padding: "12px",
        height: "220px",
        overflowY: "auto",
        fontFamily: "Consolas, Monaco, monospace",
        fontSize: "12px",
        color: "#4ade80",
    },
    terminalHeader: {
        color: "#94a3b8",
        borderBottom: "1px solid #1e293b",
        paddingBottom: "4px",
        marginBottom: "8px",
        fontSize: "11px",
        textTransform: "uppercase",
    },
};
