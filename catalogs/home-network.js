[
  {
    "name": "homeassistant",
    "image": "ghcr.io/home-assistant/home-assistant:stable",
    "default_port": 8123,
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
      "8123": "8123"
    },
    "restart_policy": "unless-stopped"
  },
  {
    "name": "portainer",
    "image": "portainer/portainer-ce:latest",
    "default_port": 9000,
    "volumes": {
      "/var/run/docker.sock": "/var/run/docker.sock",
      "/path/to/data": "/data"
    },
    "environment": {
      "PUID": "1000",
      "PGID": "1000",
      "TZ": "America/Los_Angeles"
    },
    "network_mode": "bridge",
    "ports": {
      "9000": "9000"
    },
    "restart_policy": "unless-stopped"
  },
  {
    "name": "pi-hole",
    "image": "pihole/pihole:latest",
    "default_port": 80,
    "volumes": {
      "/path/to/etc-pihole": "/etc/pihole",
      "/path/to/etc-dnsmasq.d": "/etc/dnsmasq.d"
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
    "name": "unifi-controller",
    "image": "linuxserver/unifi-controller:latest",
    "default_port": 8443,
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
      "8443": "8443"
    },
    "restart_policy": "unless-stopped"
  },
  {
    "name": "wireguard",
    "image": "linuxserver/wireguard:latest",
    "default_port": 51820,
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
      "51820": "51820"
    },
    "restart_policy": "unless-stopped"
  }
]
