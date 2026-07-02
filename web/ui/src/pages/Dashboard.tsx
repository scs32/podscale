import { useCallback, useEffect, useState } from "react";
import type { CatalogItem, Pod } from "../types";
import { api } from "../api";
import { PodCard } from "../components/PodCard";
import { CatalogCard } from "../components/CatalogCard";
import { LogsModal } from "../components/LogsModal";
import { GridIcon } from "../components/Icons";

export function Dashboard() {
  const [pods, setPods] = useState<Pod[] | null>(null);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [error, setError] = useState<string>("");
  const [logsFor, setLogsFor] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [p, c] = await Promise.all([api.pods(), api.catalog()]);
      setPods(p);
      setCatalog(c);
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 6000); // keep pod state fresh
    return () => clearInterval(t);
  }, [refresh]);

  const running = pods?.filter((p) => p.state === "running").length ?? 0;

  return (
    <>
      <h1 className="page-title">Dashboard</h1>
      <p style={{ color: "var(--muted)", margin: 0 }}>
        {pods === null
          ? "Loading…"
          : `${pods.length} pod${pods.length === 1 ? "" : "s"} · ${running} running · every service on its own tailnet identity`}
      </p>

      {error && (
        <div className="alert alert--err" style={{ marginTop: "var(--sp-5)" }}>
          <div>Couldn’t reach the controller API: {error}</div>
        </div>
      )}

      <div className="section-title">Deployed</div>
      {pods && pods.length === 0 ? (
        <div className="empty">
          <GridIcon className="empty__icon" />
          <div className="empty__title">No pods deployed yet</div>
          <p style={{ margin: 0 }}>Install a service from the catalog below.</p>
        </div>
      ) : (
        <div className="grid">
          {pods?.map((pod) => (
            <PodCard
              key={pod.name}
              pod={pod}
              onChanged={refresh}
              onLogs={setLogsFor}
            />
          ))}
        </div>
      )}

      <div className="section-title">Catalog</div>
      <div className="grid">
        {catalog.map((item) => (
          <CatalogCard key={item.name} item={item} />
        ))}
      </div>

      {logsFor && <LogsModal name={logsFor} onClose={() => setLogsFor(null)} />}
    </>
  );
}
