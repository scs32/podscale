import { useCallback, useEffect, useState } from "react";
import type { NetworkEntry } from "../types";
import { api } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FlashView, useFlash } from "../components/Flash";
import { SpinnerIcon } from "../components/Icons";

import { dnsUrl, ipUrl } from "../lib/urls";

// Per-pod networking: tailnet identity (IP + MagicDNS name) and the
// tailscale / HTTPS-serve switches. Flipping a switch re-renders the pod's
// scripts and restarts it. Polls while mounted so enrolling sidecars and
// busy pods settle into their real state without a reload.
export function Network() {
  const [entries, setEntries] = useState<NetworkEntry[] | null>(null);
  const { flash, show, clear } = useFlash();
  const [busy, setBusy] = useState<string>(""); // "<pod>:<what>"
  const [confirmTs, setConfirmTs] = useState<string | null>(null); // pod pending TS disable

  const refresh = useCallback(async () => {
    try {
      setEntries(await api.network());
    } catch (e) {
      show({ kind: "err", text: String(e) });
    }
  }, [show]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 10000); // settle enrolling/busy pods
    return () => clearInterval(t);
  }, [refresh]);

  async function apply(pod: string, what: string, body: { tailscale?: boolean; https?: boolean }) {
    setBusy(`${pod}:${what}`);
    try {
      const r = await api.networkSet(pod, body);
      show(
        r.ok
          ? { kind: "ok", text: `${pod}: network updated.` }
          : { kind: "err", text: r.error ?? r.output ?? "Failed." },
      );
      await refresh();
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <h1 className="page-title">Network</h1>
      <p style={{ color: "var(--muted)", margin: 0 }}>
        Each pod's tailnet identity and how it's exposed. Changes re-render the
        pod's scripts and restart it.
      </p>

      <FlashView flash={flash} onClose={clear} />

      <div className="section-title">Pods</div>
      {entries === null ? (
        <p style={{ color: "var(--muted)", margin: 0 }}>Loading…</p>
      ) : entries.length === 0 ? (
        <p style={{ color: "var(--muted)", margin: 0 }}>No pods deployed.</p>
      ) : (
        <div className="row-list">
          {entries.map((e) => (
            <div key={e.name} className="row card">
              <span className={`state-dot state-dot--${e.state}`} title={e.state} />
              <div style={{ minWidth: 120 }}>
                <div className="row__title">{e.name}</div>
                <div className="row__meta">
                  {e.tailscale ? (
                    <>
                      {e.dns_name ? (
                        <a
                          href={dnsUrl(e)}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={`Open ${dnsUrl(e)}`}
                        >
                          {e.dns_name}
                        </a>
                      ) : (
                        "(enrolling…)"
                      )}
                      {e.ip && (
                        <>
                          {" · "}
                          <a
                            href={ipUrl(e)}
                            target="_blank"
                            rel="noopener noreferrer"
                            title={`Open ${ipUrl(e)}`}
                          >
                            {e.ip}
                          </a>
                        </>
                      )}
                    </>
                  ) : Object.keys(e.ports).length ? (
                    `published ports: ${Object.entries(e.ports)
                      .map(([h, c]) => `${h}→${c}`)
                      .join(", ")}`
                  ) : (
                    "no tailnet identity, no published ports"
                  )}
                </div>
              </div>
              <div className="spacer" />
              {e.busy && <span className="chip chip--busy">{e.busy}…</span>}
              {e.tailscale && (
                <span className="chip chip--installed">tailscale</span>
              )}
              {e.https ? (
                <span className="chip chip--installed">https</span>
              ) : (
                <span className="chip">http</span>
              )}
              {e.controller ? (
                <span className="preview-label">controller — managed by bootstrap</span>
              ) : (
                <>
                  {e.tailscale ? (
                    <>
                      <button
                        className={
                          "btn btn--ghost btn--sm" +
                          (busy === `${e.name}:https` ? " btn--loading" : "")
                        }
                        disabled={!!busy || !!e.busy}
                        title={
                          e.https
                            ? "Stop terminating HTTPS via tailscale serve"
                            : "Terminate HTTPS on 443 via tailscale serve"
                        }
                        onClick={() => apply(e.name, "https", { https: !e.https })}
                      >
                        {busy === `${e.name}:https` && <SpinnerIcon className="btn-icon" />}
                        {e.https ? "Disable HTTPS" : "Enable HTTPS"}
                      </button>
                      <button
                        className={
                          "btn btn--danger btn--sm" +
                          (busy === `${e.name}:ts` ? " btn--loading" : "")
                        }
                        disabled={!!busy || !!e.busy}
                        title="Remove this pod's tailnet identity and publish its ports locally instead"
                        onClick={() => setConfirmTs(e.name)}
                      >
                        {busy === `${e.name}:ts` && <SpinnerIcon className="btn-icon" />}
                        Remove TS
                      </button>
                    </>
                  ) : (
                    <button
                      className={
                        "btn btn--secondary btn--sm" +
                        (busy === `${e.name}:ts` ? " btn--loading" : "")
                      }
                      disabled={!!busy || !!e.busy}
                      title="Give this pod its own tailnet identity (uses its existing Tailscale state or key file)"
                      onClick={() => apply(e.name, "ts", { tailscale: true, https: true })}
                    >
                      {busy === `${e.name}:ts` && <SpinnerIcon className="btn-icon" />}
                      Enable TS
                    </button>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {confirmTs && (
        <ConfirmDialog
          title={`Remove ${confirmTs}'s tailnet identity?`}
          confirmLabel="Remove TS"
          busy={busy === `${confirmTs}:ts`}
          onConfirm={async () => {
            const pod = confirmTs;
            await apply(pod, "ts", { tailscale: false, https: false });
            setConfirmTs(null);
          }}
          onCancel={() => setConfirmTs(null)}
        >
          The pod stops being a device on your tailnet — its MagicDNS name and
          HTTPS certificate stop working, and its ports get published on the
          host instead. Its Tailscale state is kept, so re-enabling restores
          the same identity.
        </ConfirmDialog>
      )}
    </>
  );
}
