const statusBox = document.querySelector("#run-status");
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function brute() {
  for (let i = 0; i < 6; i += 1) {
    await fetch("/demo/auth-attempt", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: "outcome=failure" });
  }
  await fetch("/demo/auth-attempt", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: "outcome=success" });
}
async function flood() { await Promise.all(Array.from({ length: 80 }, (_, i) => fetch(`/api/data?demo=${i}`, { cache: "no-store" }))); }
async function probe() { for (let i = 0; i < 22; i += 1) await fetch(`/private-probe-${i}`, { cache: "no-store" }); }
async function ports() { for (let i = 0; i < 20; i += 1) await fetch(`/demo/port/${3000 + i}`, { cache: "no-store" }); }
async function errors() { for (let i = 0; i < 16; i += 1) await fetch(`/demo/error?attempt=${i}`, { cache: "no-store" }); }
const scenarios = { brute, flood, probe, ports, errors };

async function run(name) {
  document.querySelectorAll(".attack").forEach((item) => { item.disabled = true; });
  statusBox.innerHTML = `<span class="status-dot"></span>Running ${name} scenario…`;
  try {
    if (name === "combined") for (const key of Object.keys(scenarios)) { await scenarios[key](); await pause(500); }
    else await scenarios[name]();
    statusBox.innerHTML = `<span class="status-dot"></span>${name} scenario completed. Watch the ThreatLens dashboard.`;
  } catch (error) { statusBox.textContent = `Scenario failed: ${error.message}`; }
  finally { setTimeout(() => document.querySelectorAll(".attack").forEach((item) => { item.disabled = false; }), 3000); }
}
document.querySelectorAll("[data-scenario]").forEach((button) => button.addEventListener("click", () => run(button.dataset.scenario)));
