import type { CatalogItem } from "../types";
import { PodGlyph } from "./Icons";

export function CatalogCard({ item }: { item: CatalogItem }) {
  return (
    <div className="catalog-card card">
      <div className="catalog-card__head">
        <div className="pod-icon">
          <PodGlyph />
        </div>
        <div>
          <div className="pod-card__title" style={{ fontSize: "var(--fs-base)" }}>
            {item.name}
          </div>
          {item.installed ? (
            <span className="chip chip--installed">Installed</span>
          ) : (
            item.port && <span className="chip">port {item.port}</span>
          )}
        </div>
        <div className="spacer" />
        {/* Install flow lands in Phase 3; disabled placeholder for now. */}
        <button className="btn btn--primary btn--sm" disabled>
          {item.installed ? "Reinstall" : "Install"}
        </button>
      </div>
      <div className="catalog-card__meta">{item.image}</div>
    </div>
  );
}
