[
  {
    "name": "nextcloud",
    "image": "linuxserver/nextcloud:latest",
    "default_port": 443,
    "volumes": {
      "/path/to/config": "/config",
      "/path/to/data": "/data"
    },
    "environment": {
      "PUID": "1000",
      "PGID": "1000",
      "TZ": "America/Los_Angeles"
    },
    "network_mode": "bridge",
    "ports": {
      "443": "443"
    },
    "restart_policy": "unless-stopped"
  },
  {
    "name": "vaultwarden",
    "image": "vaultwarden/server:latest",
    "default_port": 80,
    "volumes": {
      "/path/to/data": "/data"
    },
    "environment": {
      "PUID": "1000",
      "PGID": "1000",
      "TZ": "America/Los_Angeles"
    },
    "network_mode": "bridge",
    "ports": {
      "80": "80"
    },
    "restart_policy": "unless-stopped"
  },
  {
    "name": "bookstack",
    "image": "linuxserver/bookstack:latest",
    "default_port": 6875,
    "volumes": {
      "/path/to/config": "/config"
    },
    "environment": {
      "PUID": "1000",
      "PGID": "1000",
      "TZ": "America/Los_Angeles"
    },
    "network_mode": "bridge",
    "ports": {
      "6875": "6875"
    },
    "restart_policy": "unless-stopped"
  },
  {
    "name": "gitea",
    "image": "gitea/gitea:latest",
    "default_port": 3000,
    "volumes": {
      "/path/to/data": "/data"
    },
    "environment": {
      "PUID": "1000",
      "PGID": "1000",
      "TZ": "America/Los_Angeles"
    },
    "network_mode": "bridge",
    "ports": {
      "3000": "3000"
    },
    "restart_policy": "unless-stopped"
  }
]
