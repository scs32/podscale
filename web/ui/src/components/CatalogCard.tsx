import type { CatalogItem } from "../types";
import { PodGlyph } from "./Icons";

// Installed state is conveyed by the card tint (green running / amber
// stopped / red crashed) — see .catalog-card--* in the stylesheet.
export function CatalogCard({
  item,
  onInstall,
  onRemove,
  onDeleteCustom,
}: {
  item: CatalogItem;
  onInstall: (name: string) => void;
  onRemove: (name: string) => void;
  // Only for source === "custom" entries that aren't installed: removes
  // the DEFINITION from the catalog (never touches a deployed pod).
  onDeleteCustom?: (name: string) => void;
}) {
  const stateClass = item.installed && item.state ? ` catalog-card--${item.state}` : "";
  return (
    <div className={`catalog-card card${stateClass}`}>
      <div className="catalog-card__head">
        <div className="pod-icon">
          <PodGlyph />
        </div>
        <div>
          <div className="pod-card__title" style={{ fontSize: "var(--fs-base)" }}>
            {item.name}
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 2 }}>
            {!item.installed && item.port && (
              <span className="chip">port {item.port}</span>
            )}
            {item.source !== "built-in" && (
              <span className="chip" title={`from source: ${item.source}`}>
                {item.source}
              </span>
            )}
          </div>
        </div>
        <div className="spacer" />
        {item.installed ? (
          <button
            className="btn btn--danger btn--sm"
            onClick={() => onRemove(item.name)}
          >
            Remove
          </button>
        ) : (
          <>
            {item.source === "custom" && onDeleteCustom && (
              <button
                className="btn btn--ghost btn--sm"
                title="Remove this definition from the catalog"
                onClick={() => onDeleteCustom(item.name)}
              >
                Delete
              </button>
            )}
            <button
              className="btn btn--primary btn--sm"
              onClick={() => onInstall(item.name)}
            >
              Install
            </button>
          </>
        )}
      </div>
      <div className="catalog-card__meta">{item.image}</div>
    </div>
  );
}
