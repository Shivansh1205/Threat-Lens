export const ADMIN_KEY_STORAGE = "threatlens-admin-key";

export const DETECTOR_GROUPS = [
  {
    key: "brute_force",
    title: "Brute Force",
    description: "Repeated failed logins for one user.",
    fields: [
      ["window_seconds", "Window", "seconds"],
      ["medium_threshold", "Medium", "failures"],
      ["high_threshold", "High", "failures"],
      ["critical_threshold", "Critical", "failures"],
    ],
  },
  {
    key: "port_scan",
    title: "Port Scan",
    description: "Distinct ports contacted by one source IP.",
    fields: [
      ["window_seconds", "Window", "seconds"],
      ["high_threshold", "High", "ports"],
      ["critical_threshold", "Critical", "ports"],
    ],
  },
  {
    key: "unusual_ip",
    title: "Unusual IP",
    description: "Logins required before unseen IP addresses are flagged.",
    fields: [["bootstrap_count", "Baseline size", "logins"]],
  },
  {
    key: "request_flood",
    title: "Request Flood",
    description: "HTTP requests from one source within the window.",
    fields: [
      ["window_seconds", "Window", "seconds"],
      ["high_threshold", "High", "requests"],
      ["critical_threshold", "Critical", "requests"],
    ],
  },
  {
    key: "path_probe",
    title: "Path Probe",
    description: "Distinct missing paths requested by one source.",
    fields: [
      ["window_seconds", "Window", "seconds"],
      ["high_threshold", "High", "paths"],
      ["critical_threshold", "Critical", "paths"],
    ],
  },
  {
    key: "server_error_spike",
    title: "Server Error Spike",
    description: "HTTP 5xx responses associated with one source.",
    fields: [
      ["window_seconds", "Window", "seconds"],
      ["high_threshold", "High", "errors"],
      ["critical_threshold", "Critical", "errors"],
    ],
  },
];

export function cloneSettings(values) {
  return JSON.parse(JSON.stringify(values));
}

export function validateDetectionSettings(values) {
  const errors = {};
  for (const group of DETECTOR_GROUPS) {
    for (const [field] of group.fields) {
      const value = values?.[group.key]?.[field];
      const max = field === "window_seconds" ? 3600 : 100000;
      if (!Number.isInteger(value) || value < 1 || value > max) {
        errors[`${group.key}.${field}`] = `Enter a whole number from 1 to ${max.toLocaleString()}.`;
      }
    }
  }

  const brute = values?.brute_force;
  if (brute && !(brute.medium_threshold < brute.high_threshold && brute.high_threshold < brute.critical_threshold)) {
    errors["brute_force.order"] = "Medium must be lower than High, and High lower than Critical.";
  }
  for (const key of ["port_scan", "request_flood", "path_probe", "server_error_spike"]) {
    const limits = values?.[key];
    if (limits && !(limits.high_threshold < limits.critical_threshold)) {
      errors[`${key}.order`] = "High must be lower than Critical.";
    }
  }
  return errors;
}
