import type { NetworkEntry } from "../types";

// Best-guess launch URLs for a pod. The MagicDNS name gets HTTPS on 443
// when tailscale serve terminates TLS, else plain http on the service's
// first port. The IP link goes straight at the service port (no cert
// warnings — the ts.net certificate only matches the DNS name).
export function dnsUrl(e: NetworkEntry): string {
  const port = Object.values(e.ports)[0];
  if (e.https) return `https://${e.dns_name}`;
  return port ? `http://${e.dns_name}:${port}` : `http://${e.dns_name}`;
}

export function ipUrl(e: NetworkEntry): string {
  const port = Object.values(e.ports)[0];
  if (port) return `http://${e.ip}:${port}`;
  return e.https ? `https://${e.ip}` : `http://${e.ip}`;
}
