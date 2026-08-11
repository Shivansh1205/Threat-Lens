export function buildMetricsQuery(filters) {
  return new URLSearchParams(
    Object.entries(filters).filter(([, value]) => value !== "" && value !== undefined && value !== null)
  ).toString();
}
