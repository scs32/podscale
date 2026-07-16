import { useCallback, useEffect, useState } from "react";
import type { Share, ShareResult } from "../types";
import { api } from "../api";
import { Field } from "../components/Form";
import { FlashView, useFlash } from "../components/Flash";

// Defining shared folders only. Attaching a share to a pod happens in the
// pod's Edit popup on the dashboard.
export function Shares() {
  const [shares, setShares] = useState<Share[]>([]);
  const { flash, show, clear } = useFlash();

  const [name, setName] = useState("");
  const [host, setHost] = useState("");
  const [cont, setCont] = useState("");
  const [ro, setRo] = useState(false);

  // Inline NFS-export editor (one share at a time).
  const [nfsFor, setNfsFor] = useState<string | null>(null);
  const [nfsClients, setNfsClients] = useState("");
  const [nfsRo, setNfsRo] = useState(true);
  const [nfsBusy, setNfsBusy] = useState(false);

  const refresh = useCallback(async () => {
    setShares(await api.shares());
  }, []);

  useEffect(() => {
    refresh().catch((e) => show({ kind: "err", text: String(e) }));
  }, [refresh]);

  function report(r: ShareResult) {
    show(
      r.ok
        ? { kind: "ok", text: r.message ?? "Done." }
        : { kind: "err", text: r.error ?? "Failed." },
    );
    refresh();
  }

  async function add() {
    report(await api.shareAdd(name, host, cont, ro));
    setName("");
    setHost("");
    setCont("");
    setRo(false);
  }

  function openNfs(s: Share) {
    setNfsFor(s.name);
    setNfsClients(s.nfs?.clients ?? "");
    setNfsRo(s.nfs?.ro ?? true);
  }

  async function applyNfs(enabled: boolean) {
    if (!nfsFor) return;
    setNfsBusy(true);
    try {
      report(await api.shareNfs(nfsFor, enabled, nfsClients, nfsRo));
      setNfsFor(null);
    } finally {
      setNfsBusy(false);
    }
  }

  return (
    <>
      <h1 className="page-title">Shared folders</h1>
      <p style={{ color: "var(--muted)", margin: 0 }}>
        Media-only mounts — the one thing allowed to pierce the pod barrier.
        Attach them to a pod via its <strong>Edit</strong> button on the
        dashboard.
      </p>

      <FlashView flash={flash} onClose={clear} />

      <div className="section-title">Defined shares</div>
      {shares.length === 0 ? (
        <p style={{ color: "var(--muted)", margin: 0 }}>
          No shared folders defined yet.
        </p>
      ) : (
        <div className="row-list" style={{ maxWidth: 640 }}>
          {shares.map((s) => (
            <div key={s.name}>
              <div className="row card">
                <div style={{ minWidth: 0 }}>
                  <div className="row__title">{s.name}</div>
                  <div className="row__meta">
                    {s.host_path} → {s.container_path}
                  </div>
                </div>
                <div className="spacer" />
                {s.nfs && <span className="chip chip--installed">NFS</span>}
                <span className={"chip" + (s.ro ? "" : " chip--installed")}>
                  {s.mode}
                </span>
                <span className="preview-label">
                  {s.used_by.length ? `used by ${s.used_by.join(", ")}` : "unused"}
                  {s.visible ? "" : " · not visible"}
                </span>
                <button
                  className="btn btn--ghost btn--sm"
                  onClick={() => (nfsFor === s.name ? setNfsFor(null) : openNfs(s))}
                >
                  NFS…
                </button>
                <button
                  className="btn btn--danger btn--sm"
                  onClick={async () => report(await api.shareDelete(s.name))}
                >
                  Delete
                </button>
              </div>
              {nfsFor === s.name && (
                <div className="card" style={{ marginTop: "var(--sp-2)" }}>
                  <p className="field__hint" style={{ marginTop: 0 }}>
                    Export <code>{s.host_path}</code> from this VM's kernel NFS
                    server — e.g. to a native Plex on the machine hosting it.
                    Mount it there as <code>nfs://&lt;vm-ip&gt;{s.host_path}</code>.
                  </p>
                  <Field
                    label="Allowed clients"
                    hint="IP, CIDR (192.168.1.0/24), or hostname — space-separated for several"
                  >
                    <input
                      className="input"
                      value={nfsClients}
                      onChange={(e) => setNfsClients(e.target.value)}
                      placeholder="192.168.1.0/24"
                    />
                  </Field>
                  <label
                    className="toggle"
                    style={{ margin: "var(--sp-2) 0 var(--sp-3)" }}
                  >
                    <input
                      type="checkbox"
                      checked={nfsRo}
                      onChange={(e) => setNfsRo(e.target.checked)}
                    />
                    <span className="toggle__track" />
                    <span>Read-only export (recommended for media players)</span>
                  </label>
                  <div className="preview-row">
                    <button
                      className={
                        "btn btn--primary btn--sm" + (nfsBusy ? " btn--loading" : "")
                      }
                      disabled={nfsBusy || !nfsClients.trim()}
                      onClick={() => applyNfs(true)}
                    >
                      {s.nfs ? "Update export" : "Enable export"}
                    </button>
                    {s.nfs && (
                      <button
                        className="btn btn--danger btn--sm"
                        disabled={nfsBusy}
                        onClick={() => applyNfs(false)}
                      >
                        Disable
                      </button>
                    )}
                    <button
                      className="btn btn--ghost btn--sm"
                      onClick={() => setNfsFor(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="section-title">Add a shared folder</div>
      <div style={{ maxWidth: 440 }}>
        <Field label="Name" hint="a–z, 0–9, dashes">
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="media"
          />
        </Field>
        <Field label="Host path">
          <input
            className="input"
            value={host}
            onChange={(e) => setHost(e.target.value)}
            placeholder="/data"
          />
        </Field>
        <Field label="Container path" hint="blank = same as host path">
          <input
            className="input"
            value={cont}
            onChange={(e) => setCont(e.target.value)}
            placeholder="/data"
          />
        </Field>
        <label className="toggle" style={{ margin: "var(--sp-2) 0 var(--sp-4)" }}>
          <input type="checkbox" checked={ro} onChange={(e) => setRo(e.target.checked)} />
          <span className="toggle__track" />
          <span>Read-only</span>
        </label>
        <div>
          <button className="btn btn--primary" disabled={!name || !host} onClick={add}>
            Add
          </button>
        </div>
      </div>
    </>
  );
}
