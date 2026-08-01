// Shared severity -> color mapping. Every place severity shows up in the UI
// (alert badges, chart colors, high-risk indicators) imports from here, so a
// given severity always looks the same across the whole dashboard rather
// than each component picking its own colors.

export const SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

// Hex values for Recharts (which takes raw colors, not Tailwind classes).
export const SEVERITY_COLORS = {
  LOW: "#38bdf8", // sky-400 - blue-ish
  MEDIUM: "#fbbf24", // amber-400 - yellow/amber
  HIGH: "#fb923c", // orange-400
  CRITICAL: "#f87171", // red-400
};

// Tailwind classes for badges/chips elsewhere in the DOM.
export const SEVERITY_BADGE_CLASSES = {
  LOW: "bg-sky-500/10 text-sky-300 ring-1 ring-inset ring-sky-500/30",
  MEDIUM: "bg-amber-500/10 text-amber-300 ring-1 ring-inset ring-amber-500/30",
  HIGH: "bg-orange-500/10 text-orange-300 ring-1 ring-inset ring-orange-500/30",
  CRITICAL: "bg-red-500/10 text-red-300 ring-1 ring-inset ring-red-500/30",
};
