import { FormSection } from "./Form";

// The one folder-editing affordance, shared by install-from-catalog, custom
// pod, and the pod Edit popup: structured host → container rows with a
// read-only flag, matching the Shares page language (host path, container
// path, read-only) instead of a raw /container=/host textarea in some places
// and per-volume fields in others.

export interface FolderRow {
  host: string; // host path, without any :ro suffix
  container: string; // path inside the container
  ro: boolean;
}

// API volume maps are container path → host path, with read-only expressed
// as a ":ro" suffix on the host path. Convert to/from editable rows.
export function volumesToRows(map: Record<string, string>): FolderRow[] {
  return Object.entries(map).map(([container, host]) => ({
    container,
    host: host.replace(/:ro$/, ""),
    ro: host.endsWith(":ro"),
  }));
}

export function rowsToVolumes(rows: FolderRow[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of rows) {
    const container = r.container.trim();
    const host = r.host.trim();
    if (container.startsWith("/") && host.startsWith("/")) {
      out[container] = host + (r.ro ? ":ro" : "");
    }
  }
  return out;
}

export function FolderEditor({
  rows,
  onChange,
}: {
  rows: FolderRow[];
  onChange: (rows: FolderRow[]) => void;
}) {
  const set = (i: number, patch: Partial<FolderRow>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <FormSection title="Folders">
      {rows.length > 0 && (
        <p className="field__hint" style={{ margin: "0 0 var(--sp-2)" }}>
          Host path → path inside the container.
        </p>
      )}
      {rows.map((r, i) => (
        <div className="folder-row" key={i}>
          <input
            className="input"
            value={r.host}
            placeholder="/host/path"
            aria-label="Host path"
            onChange={(e) => set(i, { host: e.target.value })}
          />
          <span className="folder-row__arrow">→</span>
          <input
            className="input"
            value={r.container}
            placeholder="/path/in/container"
            aria-label="Container path"
            onChange={(e) => set(i, { container: e.target.value })}
          />
          <label className="folder-row__ro" title="Mount read-only">
            <input
              type="checkbox"
              checked={r.ro}
              onChange={(e) => set(i, { ro: e.target.checked })}
            />
            ro
          </label>
          <button
            className="btn btn--ghost btn--sm"
            title="Remove this folder"
            onClick={() => onChange(rows.filter((_, j) => j !== i))}
          >
            ✕
          </button>
        </div>
      ))}
      <div>
        <button
          className="btn btn--ghost btn--sm"
          onClick={() => onChange([...rows, { host: "", container: "", ro: false }])}
        >
          + Add folder
        </button>
      </div>
      <p className="field__hint" style={{ margin: "var(--sp-2) 0 0" }}>
        Incomplete rows are dropped. For media, attach a shared folder below
        instead.
      </p>
    </FormSection>
  );
}
