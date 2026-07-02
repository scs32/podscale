// Typed client for the controller JSON API. Same-origin fetch; the dev server
// proxies /api to a locally-running app.py (see vite.config.ts).

import type { ActionResult, CatalogItem, Pod, Share } from "./types";

async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json() as Promise<T>;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  // The API returns a structured body on 4xx/5xx too; surface it to the caller.
  const data = (await r.json()) as T;
  return data;
}

export const api = {
  pods: () => getJSON<{ pods: Pod[] }>("/api/pods").then((d) => d.pods),
  catalog: () =>
    getJSON<{ catalog: CatalogItem[] }>("/api/catalog").then((d) => d.catalog),
  shares: () => getJSON<{ shares: Share[] }>("/api/shares").then((d) => d.shares),

  logs: (name: string) =>
    getJSON<ActionResult>(`/api/pods/${name}/logs`),

  action: (name: string, action: "start" | "stop" | "update") =>
    postJSON<ActionResult>(`/api/pods/${name}/action`, { do: action }),
};
