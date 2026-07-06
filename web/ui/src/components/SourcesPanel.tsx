import { useState } from "react";
import type { BuiltinCatalog, ShareResult, Source } from "../types";
import { api } from "../api";
import { Field } from "./Form";
import { FlashView, useFlash } from "./Flash";

// Rendered inside the catalog's Sources modal (the modal owns the title).
export function SourcesPanel({
  sources,
  catalogs,
  onChanged,
}: {
  sources: Source[];
  catalogs: BuiltinCatalog[];
  onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [catBusy, setCatBusy] = useState("");
  const { flash, show, clear } = useFlash();

  async function toggleCatalog(c: BuiltinCatalog) {
    setCatBusy(c.key);
    try {
      const r = await api.catalogSet(c.key, !c.enabled);
      if (!r.ok) show({ kind: "err", text: r.error ?? "Failed." });
      onChanged();
    } finally {
      setCatBusy("");
    }
  }

  function report(r: ShareResult) {
    show(
      r.ok
        ? { kind: "ok", text: r.message ?? "Done." }
        : { kind: "err", text: r.error ?? "Failed." },
    );
    onChanged();
  }

  async function add() {
    setBusy(true);
    try {
      const r = await api.sourceAdd(name.trim(), url.trim());
      report(r);
      if (r.ok) {
        setName("");
        setUrl("");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <p className="field__hint" style={{ margin: "0 0 var(--sp-4)" }}>
        Add a URL to an external catalog (homelab.js JSON schema). Its services
        appear in the catalog alongside the built-in ones.
      </p>

      <FlashView flash={flash} onClose={clear} />

      <div className="section-title" style={{ marginTop: 0 }}>Built-in catalogs</div>
      <p className="field__hint" style={{ margin: "0 0 var(--sp-3)" }}>
        The media catalog is always on. Opt into more categories:
      </p>
      <div className="row-list" style={{ marginBottom: "var(--sp-5)" }}>
        {catalogs.map((c) => (
          <label
            key={c.key}
            className="row card"
            style={{ cursor: catBusy ? "wait" : "pointer" }}
          >
            <input
              type="checkbox"
              checked={c.enabled}
              disabled={!!catBusy}
              onChange={() => toggleCatalog(c)}
            />
            <div style={{ minWidth: 0 }}>
              <div className="row__title">{c.name}</div>
              <div className="row__meta">{c.description}</div>
            </div>
            <div className="spacer" />
            <span className="preview-label">{c.service_count} services</span>
          </label>
        ))}
      </div>

      <div className="section-title">External sources</div>
      {sources.length > 0 && (
        <div className="row-list" style={{ marginBottom: "var(--sp-5)" }}>
          {sources.map((s) => (
            <div key={s.name} className="row card">
              <div style={{ minWidth: 0 }}>
                <div className="row__title">{s.name}</div>
                <div className="row__meta" title={s.url}>
                  {s.url}
                </div>
              </div>
              <div className="spacer" />
              {s.error ? (
                <span className="chip" style={{ color: "var(--danger)" }} title={s.error}>
                  error
                </span>
              ) : (
                <span className="preview-label">{s.service_count} services</span>
              )}
              <button
                className="btn btn--danger btn--sm"
                onClick={async () => report(await api.sourceDelete(s.name))}
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      )}

      <Field label="Name" hint="a–z, 0–9, dashes">
        <input
          className="input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="community"
        />
      </Field>
      <Field label="Catalog URL">
        <input
          className="input"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/catalog.json"
        />
      </Field>
      <button
        className={"btn btn--primary" + (busy ? " btn--loading" : "")}
        disabled={busy || !name.trim() || !url.trim()}
        onClick={add}
      >
        Add source
      </button>
    </>
  );
}
