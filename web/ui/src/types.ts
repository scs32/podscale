// Shapes returned by the controller JSON API (web/app.py).

export type PodState = "running" | "stopped";

export interface Pod {
  name: string;
  state: PodState;
  controller: boolean;
  image: string;
  tailscale: boolean;
  https: boolean;
  shares: string[];
}

export interface CatalogItem {
  name: string;
  image: string;
  ports: Record<string, string>;
  port: string;
  environment: Record<string, string>;
  volumes: Record<string, string>;
  command: string;
  installed: boolean;
}

export interface Share {
  name: string;
  host_path: string;
  container_path: string;
  ro: boolean;
  mode: "read-only" | "read-write";
  visible: boolean;
  used_by: string[];
}

export interface ActionResult {
  ok: boolean;
  name: string;
  action: string;
  status: string;
  error: string | null;
  output: string;
}
