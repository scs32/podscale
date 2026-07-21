// Theme selection — a theme is a token override set in styles/themes.css,
// applied via <html data-theme="…"> and persisted per-browser. Sharing /
// importing themes is a planned follow-up; keep this the single authority
// on what themes exist so a future registry can replace THEMES wholesale.

export interface Theme {
  id: string;
  name: string;
  // Swatch preview colors (must match the CSS block, duplicated here so
  // the picker can render every theme without applying it).
  bg: string;
  surface: string;
  accent: string;
  light?: boolean;
}

export const THEMES: Theme[] = [
  { id: "signal", name: "Signal", bg: "#0F172A", surface: "#1E293B", accent: "#22D3EE" },
  { id: "midnight", name: "Midnight", bg: "#0B1120", surface: "#151E33", accent: "#818CF8" },
  { id: "aurora", name: "Aurora", bg: "#0A1512", surface: "#13241F", accent: "#34D399" },
  { id: "ember", name: "Ember", bg: "#171210", surface: "#241D19", accent: "#FB923C" },
  { id: "orchid", name: "Orchid", bg: "#141021", surface: "#1F1933", accent: "#C084FC" },
  { id: "rosewood", name: "Rosewood", bg: "#191114", surface: "#261A1F", accent: "#FB7185" },
  { id: "nord", name: "Nord", bg: "#2E3440", surface: "#3B4252", accent: "#88C0D0" },
  { id: "synthwave", name: "Synthwave", bg: "#16102B", surface: "#221741", accent: "#F472B6" },
  { id: "graphite", name: "Graphite", bg: "#121316", surface: "#1C1E22", accent: "#D3D7DE" },
  { id: "paper", name: "Paper", bg: "#EEF2F6", surface: "#FFFFFF", accent: "#0891B2", light: true },
];

const KEY = "tailarr.theme";

export function currentTheme(): string {
  try {
    const t = localStorage.getItem(KEY) ?? "signal";
    return THEMES.some((x) => x.id === t) ? t : "signal";
  } catch {
    return "signal";
  }
}

export function applyTheme(id: string) {
  const root = document.documentElement;
  if (id === "signal") delete root.dataset.theme;
  else root.dataset.theme = id;
  try {
    if (id === "signal") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, id);
  } catch {
    // private mode — theme just won't persist
  }
}

// Called once at boot (main.tsx) so the stored theme paints before React.
export function initTheme() {
  applyTheme(currentTheme());
}
