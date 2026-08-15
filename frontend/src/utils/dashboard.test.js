import assert from "node:assert/strict";
import test from "node:test";
import { getThreatType, humanizeThreatType } from "../constants/threatTypes.js";
import { buildMetricsQuery } from "./reporting.js";
import { getInitialTheme, THEME_STORAGE_KEY } from "./theme.js";
import { cloneSettings, validateDetectionSettings } from "./detectionSettings.js";

test("theme defaults to light and restores only an explicit dark choice", () => {
  assert.equal(getInitialTheme({ getItem: () => null }), "light");
  assert.equal(getInitialTheme({ getItem: (key) => key === THEME_STORAGE_KEY ? "dark" : null }), "dark");
  assert.equal(getInitialTheme({ getItem: () => "system" }), "light");
});

test("report query omits empty filters but preserves false", () => {
  const query = new URLSearchParams(buildMetricsQuery({ severity: "", resolved: false, bucket_minutes: 30 }));
  assert.equal(query.has("severity"), false);
  assert.equal(query.get("resolved"), "false");
  assert.equal(query.get("bucket_minutes"), "30");
});

test("threat metadata supports known and future detector types", () => {
  assert.equal(getThreatType("path_probe").label, "Path Probe");
  assert.equal(getThreatType("new_detector").label, "New Detector");
  assert.equal(humanizeThreatType("server_error_spike"), "Server Error Spike");
});

const validLimits = {
  brute_force: { window_seconds: 60, medium_threshold: 5, high_threshold: 10, critical_threshold: 20 },
  port_scan: { window_seconds: 3, high_threshold: 15, critical_threshold: 50 },
  unusual_ip: { bootstrap_count: 3 },
  request_flood: { window_seconds: 10, high_threshold: 30, critical_threshold: 75 },
  path_probe: { window_seconds: 60, high_threshold: 8, critical_threshold: 20 },
  server_error_spike: { window_seconds: 60, high_threshold: 5, critical_threshold: 15 },
};

test("detection settings validation accepts original documented defaults", () => {
  assert.deepEqual(validateDetectionSettings(validLimits), {});
});

test("detection settings validation rejects bad ordering and bounds", () => {
  const invalid = cloneSettings(validLimits);
  invalid.brute_force.medium_threshold = 10;
  invalid.brute_force.high_threshold = 10;
  invalid.path_probe.window_seconds = 0;
  const errors = validateDetectionSettings(invalid);
  assert.ok(errors["brute_force.order"]);
  assert.ok(errors["path_probe.window_seconds"]);
});
