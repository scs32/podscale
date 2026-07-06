import { useCallback, useEffect, useState } from "react";
import type { UsersStatus } from "../types";
import { api } from "../api";
import { Alert } from "../components/Alert";
import { FlashView, useFlash } from "../components/Flash";

function ago(iso: string): string {
  if (!iso) return "";
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 2) return "online";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 48 * 60) return `${Math.floor(mins / 60)}h ago`;
  return `${Math.floor(mins / 1440)}d ago`;
}

// User machines: devices enrolled with a podscale-user auth key. Each machine
// can reach exactly the services it holds a capability badge for — checkboxes
// here flip tag:podscale-can-<svc> on the device via the Tailscale API. No
// policy-file changes, effective in seconds. See docs/acl-design.md.
export function Users() {
  const [status, setStatus] = useState<UsersStatus | null>(null);
  const [busyKey, setBusyKey] = useState(""); // "<id>:<svc>" or "<id>:nick"
  const [nickEdit, setNickEdit] = useState<{ id: string; value: string } | null>(null);
  const { flash, show, clear } = useFlash();

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.users());
    } catch (e) {
      show({ kind: "err", text: String(e) });
    }
  }, [show]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [refresh]);

  async function toggle(id: string, service: string, allow: boolean) {
    setBusyKey(`${id}:${service}`);
    try {
      const r = await api.userAccess(id, service, allow);
      if (!r.ok) show({ kind: "err", text: r.error ?? "Failed to update access." });
      await refresh();
    } catch (e) {
      show({ kind: "err", text: String(e) });
    } finally {
      setBusyKey("");
    }
  }

  async function saveNick(id: string, nickname: string) {
    setNickEdit(null);
    setBusyKey(`${id}:nick`);
    try {
      await api.userNick(id, nickname);
      await refresh();
    } finally {
      setBusyKey("");
    }
  }

  return (
    <>
      <h1 className="page-title">Users</h1>
      <p style={{ color: "var(--muted)", margin: 0 }}>
        Machines enrolled with a Podscale user key. A machine reaches only the
        services checked here — changes apply in seconds, no restarts.
      </p>

      <FlashView flash={flash} onClose={clear} />

      {status === null ? (
        <p style={{ color: "var(--muted)", marginTop: "var(--sp-5)" }}>Loading…</p>
      ) : !status.configured ? (
        <div style={{ marginTop: "var(--sp-5)" }}>
          <Alert kind="info">
            No Tailscale API token on the controller. Create one in the
            Tailscale admin console (Settings → Keys) and store it as{" "}
            <code>{'{"token": "..."}'}</code> in <code>Pods/.tsapi.json</code>.
          </Alert>
        </div>
      ) : status.error ? (
        <div style={{ marginTop: "var(--sp-5)" }}>
          <Alert kind="err">{status.error}</Alert>
        </div>
      ) : status.users.length === 0 ? (
        <div className="empty" style={{ marginTop: "var(--sp-5)" }}>
          <div className="empty__title">No user machines yet</div>
          <p style={{ margin: 0 }}>
            Hand out an auth key tagged <code>tag:podscale-user</code> — devices
            that enroll with it appear here with zero access until you grant it.
          </p>
        </div>
      ) : (
        <>
          <div className="section-title">Machines</div>
          <div className="row-list">
            {status.users.map((u) => (
              <div key={u.id} className="row card" style={{ flexWrap: "wrap" }}>
                <div style={{ minWidth: 180 }}>
                  {nickEdit?.id === u.id ? (
                    <input
                      className="input"
                      autoFocus
                      value={nickEdit.value}
                      placeholder={u.hostname}
                      onChange={(e) => setNickEdit({ id: u.id, value: e.target.value })}
                      onBlur={() => saveNick(u.id, nickEdit.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveNick(u.id, nickEdit.value);
                        if (e.key === "Escape") setNickEdit(null);
                      }}
                    />
                  ) : (
                    <div
                      className="row__title"
                      title="Click to set a nickname"
                      style={{ cursor: "pointer" }}
                      onClick={() => setNickEdit({ id: u.id, value: u.nickname })}
                    >
                      {u.nickname || u.hostname}
                    </div>
                  )}
                  <div className="row__meta">
                    {u.nickname && `${u.hostname} · `}
                    {u.os} · {ago(u.last_seen)}
                    {u.ip && ` · ${u.ip}`}
                  </div>
                </div>
                <div className="spacer" />
                <div className="preview-row" style={{ gap: "var(--sp-3)" }}>
                  {status.services.map((svc) => {
                    const allowed = u.can.includes(svc);
                    const busy = busyKey === `${u.id}:${svc}`;
                    return (
                      <label
                        key={svc}
                        className="field__hint"
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          cursor: busy ? "wait" : "pointer",
                          opacity: busy ? 0.5 : 1,
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={allowed}
                          disabled={!!busyKey}
                          onChange={() => toggle(u.id, svc, !allowed)}
                        />
                        {svc}
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
