import { useState } from "react";
import { api } from "../api";
import { SpinnerIcon } from "./Icons";

// One-shot shell into a pod's main container: type a command, run it, see
// stdout/stderr + exit status. No session state — each Run is a fresh
// `podman exec <pod> sh -c '…'` on the server.
export function ExecModal({ name, onClose }: { name: string; onClose: () => void }) {
  const [cmd, setCmd] = useState("");
  const [text, setText] = useState("");
  const [status, setStatus] = useState("");
  const [running, setRunning] = useState(false);

  async function run() {
    if (!cmd.trim() || running) return;
    setRunning(true);
    setStatus("");
    try {
      const r = await api.exec(name, cmd);
      setText(r.output || (r.error ?? "(no output)"));
      setStatus(r.error && !r.output ? "error" : r.status);
    } catch (e) {
      setText(String(e));
      setStatus("error");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="scrim" onClick={onClose}>
      <div
        className="log"
        style={{ width: "min(720px, 100%)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="log__bar">
          <span className="log__dot" />
          <span className="log__name">
            {name} · shell{status && ` · ${status}`}
          </span>
          <div className="spacer" />
          <button className="btn btn--ghost btn--sm" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="log__bar">
          <input
            className="input"
            style={{ flex: 1, fontFamily: "monospace" }}
            placeholder="command, e.g. ls /config"
            value={cmd}
            autoFocus
            onChange={(e) => setCmd(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && run()}
          />
          <button
            className={"btn btn--primary btn--sm" + (running ? " btn--loading" : "")}
            disabled={running || !cmd.trim()}
            onClick={run}
          >
            {running && <SpinnerIcon className="btn-icon" />}
            Run
          </button>
        </div>
        <div className="log__body">{text || "Run a command to see its output."}</div>
      </div>
    </div>
  );
}
