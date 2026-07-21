import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { FolderIcon, SpinnerIcon } from "./Icons";

// "Browse" popover for host-path fields (FolderEditor): navigate the PODMAN
// HOST's directories via POST /api/fs instead of typing paths blind — the
// picker prevents the "folder not found on host" state entirely. Each
// listing runs in a one-shot helper container on the host, so navigation
// has a short spinner rather than being instant.

export function FolderBrowser({
  value,
  onPick,
}: {
  value: string; // current host-path field value (starting point when absolute)
  onPick: (path: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [path, setPath] = useState("/");
  const [parent, setParent] = useState<string | null>(null);
  const [dirs, setDirs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [newName, setNewName] = useState<string | null>(null); // null = closed
  const [creating, setCreating] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const seq = useRef(0); // drop out-of-order responses from fast clicks

  // close on outside click / Escape (same affordance as ChipPicker)
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const load = async (p: string, fallbackToRoot = false) => {
    const mine = ++seq.current;
    setLoading(true);
    setError("");
    setNewName(null);
    try {
      const r = await api.fsList(p);
      if (mine !== seq.current) return;
      if (r.ok) {
        setPath(r.path);
        setParent(r.parent);
        setDirs(r.dirs);
      } else if (fallbackToRoot && p !== "/") {
        void load("/");
        return;
      } else {
        setError(r.error ?? "Could not list that folder.");
      }
    } catch (e) {
      if (mine === seq.current) setError(String(e));
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  };

  const toggle = () => {
    const opening = !open;
    setOpen(opening);
    // start where the field points; a not-yet-existing path falls back to /
    if (opening) void load(value.trim().startsWith("/") ? value.trim() : "/", true);
  };

  const join = (dir: string) => (path === "/" ? "" : path) + "/" + dir;

  const create = async () => {
    const name = (newName ?? "").trim();
    if (!name || name.includes("/")) return;
    setCreating(true);
    setError("");
    try {
      const r = await api.fsMkdir(join(name));
      if (r.ok) void load(r.path);
      else setError(r.error ?? "Could not create the folder.");
    } catch (e) {
      setError(String(e));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="fs-browse" ref={rootRef}>
      <button
        type="button"
        className="btn btn--ghost btn--sm"
        title="Browse host folders"
        onClick={toggle}
      >
        <FolderIcon width={14} height={14} />
      </button>

      {open && (
        <div className="picker-pop fs-pop card">
          <div className="fs-pop__path" title={path}>
            {loading && <SpinnerIcon className="chip__spin" />}
            <span>{path}</span>
          </div>

          <div className="picker-pop__list">
            {parent !== null && (
              <button
                type="button"
                className="picker-item"
                disabled={loading}
                onClick={() => void load(parent)}
              >
                <FolderIcon className="fs-pop__icon" />
                <span>..</span>
              </button>
            )}
            {dirs.map((d) => (
              <button
                type="button"
                key={d}
                className="picker-item"
                disabled={loading}
                onClick={() => void load(join(d))}
              >
                <FolderIcon className="fs-pop__icon" />
                <span>{d}</span>
              </button>
            ))}
            {!loading && !error && dirs.length === 0 && (
              <span className="field__hint" style={{ padding: "var(--sp-2)" }}>
                No subfolders.
              </span>
            )}
          </div>

          {error && <p className="field__error fs-pop__error">{error}</p>}

          {newName === null ? (
            <div className="fs-pop__actions">
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                disabled={loading}
                onClick={() => setNewName("")}
              >
                + New folder
              </button>
              <button
                type="button"
                className="btn btn--primary btn--sm"
                disabled={loading || !!error}
                onClick={() => {
                  onPick(path);
                  setOpen(false);
                }}
              >
                Choose this folder
              </button>
            </div>
          ) : (
            <div className="fs-pop__actions">
              <input
                className="input"
                autoFocus
                placeholder="folder name"
                value={newName}
                disabled={creating}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void create()}
              />
              <button
                type="button"
                className="btn btn--primary btn--sm"
                disabled={creating || !newName.trim() || newName.includes("/")}
                onClick={() => void create()}
              >
                {creating ? <SpinnerIcon className="chip__spin" /> : "Create"}
              </button>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                disabled={creating}
                onClick={() => setNewName(null)}
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
