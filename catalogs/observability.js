[
  {
    "name": "grafana",
    "image": "grafana/grafana:latest",
    "restart_policy": "unless-stopped",
    "environment": { "TZ": "America/Los_Angeles" },
    "volumes": { "/var/lib/grafana": "grafana-data" },
    "ports": { "3000": "3000" }
  },
  {
    "name": "prometheus",
    "image": "prom/prometheus:latest",
    "restart_policy": "unless-stopped",
    "environment": {},
    "volumes": { "/prometheus": "prometheus-data", "/etc/prometheus": "prometheus-config" },
    "ports": { "9090": "9090" }
  }
]
