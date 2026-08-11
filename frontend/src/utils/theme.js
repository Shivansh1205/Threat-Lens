export const THEME_STORAGE_KEY = "threatlens-theme";

export function getInitialTheme(storage) {
  return storage?.getItem(THEME_STORAGE_KEY) === "dark" ? "dark" : "light";
}
