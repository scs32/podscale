import { useState } from "react";
import { CheckIcon } from "./Icons";
import { THEMES, applyTheme, currentTheme } from "../lib/theme";

// Settings → Themes: the whole app is skinned by CSS token override sets
// (styles/themes.css); picking one applies instantly and persists in this
// browser. Sharing themes with others is a planned follow-up.
export function ThemesCard() {
  const [active, setActive] = useState(currentTheme());

  return (
    <>
      <p className="field__hint" style={{ margin: "0 0 var(--sp-4)" }}>
        Skins the whole app — applied instantly, remembered per browser.
        Sharing your own themes is planned.
      </p>
      <div className="theme-grid">
        {THEMES.map((t) => (
          <button
            key={t.id}
            className={
              "theme-swatch" + (active === t.id ? " theme-swatch--active" : "")
            }
            title={`Switch to ${t.name}`}
            onClick={() => {
              applyTheme(t.id);
              setActive(t.id);
            }}
          >
            <div
              className="theme-swatch__preview"
              style={{ background: t.bg }}
            >
              <div
                className="theme-swatch__bar"
                style={{ background: t.surface }}
              />
              <div className="theme-swatch__dots">
                <span
                  className="theme-swatch__dot"
                  style={{ background: t.accent }}
                />
                <span
                  className="theme-swatch__dot"
                  style={{ background: t.surface, opacity: 0.9 }}
                />
                <span
                  className="theme-swatch__bar"
                  style={{ background: t.surface, flex: 1, height: 7 }}
                />
              </div>
            </div>
            <span className="theme-swatch__name">
              {active === t.id && (
                <CheckIcon
                  style={{ width: 14, height: 14, color: "var(--accent)" }}
                />
              )}
              {t.name}
            </span>
          </button>
        ))}
      </div>
    </>
  );
}
