#!/usr/bin/env python3
"""End-to-end test of the web controller JSON API.

Boots the real ThreadingHTTPServer against the create.sh engine in a temp
PODS_DIR and drives it over HTTP. No podman/containers needed: installing only
generates scripts, and pod-state reads degrade gracefully when podman is absent
(podman() catches FileNotFoundError). Tailscale is mandatory, so installs
carry a dummy auth key (only stored in a key file, never used offline).
"""
import json
import os
import sys
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pods = os.path.join(tempfile.mkdtemp(), "Pods")
os.makedirs(pods)
os.environ["APP_DIR"] = REPO
os.environ["PODS_DIR"] = pods
# Point STATIC_DIR at a definitely-absent dir so the JSON API + legacy HTML win.
os.environ["STATIC_DIR"] = os.path.join(pods, "no-such-static")
sys.path.insert(0, os.path.join(REPO, "web"))
import app  # noqa: E402

srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"

# A tiny local server that serves an external catalog (homelab.js schema),
# so the catalog-sources test exercises the real fetch/merge path offline.
CATALOG_JSON = json.dumps([
    {"name": "extpod", "image": "docker.io/alpine:latest",
     "command": "sleep infinity", "ports": {}, "environment": {}, "volumes": {},
     "network_mode": "bridge", "restart_policy": "unless-stopped"},
]).encode()


class CatalogHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(CATALOG_JSON)))
        self.end_headers()
        self.wfile.write(CATALOG_JSON)

    def log_message(self, *a):  # keep test output quiet
        pass


catsrv = ThreadingHTTPServer(("127.0.0.1", 0), CatalogHandler)
threading.Thread(target=catsrv.serve_forever, daemon=True).start()
CAT_URL = f"http://127.0.0.1:{catsrv.server_address[1]}/catalog.json"


def check(cond, label):
    if not cond:
        print(f"FAIL: {label}")
        srv.shutdown()
        sys.exit(1)
    print(f"  ok: {label}")


def get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return r.status, json.load(r)


def post(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


# --- catalog ---
code, data = get("/api/catalog")
check(code == 200 and isinstance(data.get("catalog"), list) and data["catalog"],
      "GET /api/catalog returns entries")
check(all("name" in c and "image" in c and "installed" in c for c in data["catalog"]),
      "catalog entries carry name/image/installed")

# --- install a custom pod over the API ---
code, data = post("/api/install", {
    "custom": True, "service": "apitest", "image": "docker.io/alpine:latest",
    "command": "sleep infinity",
    "volumes": {"/config": f"{pods}/apitest/config"},
    "authkey": "dummy-test-authkey-api",
})
check(code == 200 and data["ok"] and data["name"] == "apitest",
      "POST /api/install (custom) succeeds")
check(os.path.isfile(os.path.join(pods, "apitest", "run.sh")),
      "install generated run.sh")
check(app.pod_config("apitest")["image"] == "docker.io/alpine:latest",
      ".config.json written")

# --- it shows up in /api/pods ---
code, data = get("/api/pods")
names = {p["name"]: p for p in data["pods"]}
check(code == 200 and "apitest" in names, "GET /api/pods lists the new pod")
check(names["apitest"]["state"] == "stopped" and names["apitest"]["controller"] is False,
      "pod reported stopped / non-controller")

# --- shares: add then attach via the API ---
code, data = post("/api/shares", {"do": "add", "name": "media", "host_path": "/data"})
check(code == 200 and data["ok"], "POST /api/shares add")
code, data = get("/api/shares")
check(any(s["name"] == "media" and s["mode"] == "read-write" for s in data["shares"]),
      "GET /api/shares lists it")
code, data = post("/api/shares", {"do": "attach", "pod": "apitest", "share": "media"})
check(code == 200 and data["ok"], "POST /api/shares attach")
check(app.pod_config("apitest")["shares"] == ["media"], "share recorded on the pod")

# --- built-in category catalogs: off by default, toggle merges entries ---
code, data = get("/api/sources")
check(code == 200 and any(c["key"] == "observability" for c in data["catalogs"]),
      "sources: built-in catalogs listed")
check(all(not c["enabled"] for c in data["catalogs"]),
      "catalogs: all categories default off")
code, data = get("/api/catalog")
check(not any(c["name"] == "grafana" for c in data["catalog"]),
      "catalog: category entries hidden until enabled")
code, data = post("/api/catalogs", {"key": "observability", "enabled": True})
check(code == 200 and data["ok"], "enable the observability catalog")
code, data = get("/api/catalog")
g = [c for c in data["catalog"] if c["name"] == "grafana"]
check(bool(g) and g[0]["source"] == "Observability",
      "grafana appears, tagged with its category")
check(post("/api/catalogs", {"key": "bogus", "enabled": True})[0] == 400,
      "unknown catalog key rejected")
code, data = post("/api/catalogs", {"key": "observability", "enabled": False})
check(code == 200 and not any(
    c["name"] == "grafana"
    for c in get("/api/catalog")[1]["catalog"]), "disable removes the entries")

# --- /metrics: Prometheus exposition (no podman here -> flags only) ---
with urllib.request.urlopen(BASE + "/metrics") as r:
    text = r.read().decode()
    check(r.status == 200 and 'tailarr_pod_up{pod="apitest"}' in text,
          "/metrics exposes the pod up gauge")
    check("tailarr_pod_public" in text and "tailarr_pod_update_available" in text,
          "/metrics exposes funnel + update flags")

# --- validation / error paths ---
code, data = post("/api/install", {"service": "definitely-not-real"})
check(code == 400 and data["ok"] is False and "Unknown service" in data["error"],
      "unknown catalog service -> 400")
code, data = post("/api/pods/nope/action", {"do": "start"})
check(code == 400 and data["ok"] is False, "action on unknown pod -> 400")
code, data = post("/api/shares", {"do": "bogus"})
check(code == 400 and "Unknown action" in data["error"], "bad share action -> 400")
code, data = post("/api/fleet", {"do": "bogus"})
check(code == 400 and "Unknown fleet action" in data["error"], "bad fleet action -> 400")
# No podman here, so nothing reads as running: fleet stop is a clean no-op.
code, data = post("/api/fleet", {"do": "stop"})
check(code == 200 and data["ok"] and data["results"] == [],
      "fleet stop with nothing running -> 200 no-op")

try:
    get("/api/nope")
    check(False, "unknown API path -> 404")
except urllib.error.HTTPError as e:
    check(e.code == 404, "unknown API path -> 404")

# --- deploys leave their log in the service dir (bad-CWD regression) ---
check(os.path.isfile(os.path.join(pods, "apitest", ".deployment.log")),
      "install wrote .deployment.log into the pod dir (absolute LOG_FILE)")

# --- credential wizard: status + validate/save/fences, no credential yet ---
code, data = get("/api/info")
check(code == 200 and data.get("version") and data.get("tsapi") is not None,
      "GET /api/info carries version + tsapi state")
code, data = get("/api/tsapi")
check(code == 200 and data["configured"] is False,
      "GET /api/tsapi: not configured on a fresh install")
code, data = post("/api/tsapi/validate", {})
check(data["ok"] is False and "credential" in (data["error"] or "").lower(),
      "validate with no credential explains itself")
code, data = post("/api/tsapi", {})
check(code == 400 and data["ok"] is False,
      "save with no credential -> 400")
code, data = post("/api/tsapi/fences", {})
check(code == 400 and "no API token" in (data["error"] or ""),
      "fence init without a credential -> 400")

# --- install without a key and without a credential: the wizard trigger ---
code, data = post("/api/install", {
    "custom": True, "service": "nokey", "image": "docker.io/alpine:latest"})
check(code == 400 and data["ok"] is False
      and "auth key is required" in data["error"]
      and "Settings" in data["error"],
      "keyless install without a credential -> 400, points at the wizard")

# --- auto-mint: with a credential + stubbed keys API, zero manual entry ---
_real_ts_token = app._ts_token
_real_ts_api = app.ts_api
_real_policy_sync = app.ts_policy_sync
minted = {}


def _fake_ts_api(method, path, body=None):
    if method == "POST" and path == "/tailnet/-/keys":
        minted["body"] = body
        return 200, {"key": "dummy-test-authkey-minted"}
    return 200, {}


app._ts_token = lambda: "dummy-test-token"
app.ts_api = _fake_ts_api
app.ts_policy_sync = lambda: {"ok": True, "changed": False, "error": None}
try:
    code, data = post("/api/install", {
        "custom": True, "service": "autominted",
        "image": "docker.io/alpine:latest", "command": "sleep infinity"})
    check(code == 200 and data["ok"],
          "keyless install with a credential auto-mints and succeeds")
    keyfile = os.path.join(pods, "autominted", ".tailscale_authkey")
    check(os.path.isfile(keyfile)
          and open(keyfile).read().strip() == "dummy-test-authkey-minted",
          "minted key written to the pod's key file")
    check(os.stat(keyfile).st_mode & 0o777 == 0o600,
          "minted key file is 0600")
    caps = minted["body"]["capabilities"]["devices"]["create"]
    check(caps["tags"] == ["tag:tailarr"] and caps["preauthorized"] is True
          and caps["reusable"] is False and caps["ephemeral"] is False,
          "minted key is single-use, preauthorized, tagged tag:tailarr")
    check(minted["body"]["expirySeconds"] > 0
          and "autominted" in minted["body"]["description"],
          "minted key has a TTL and a descriptive description")
    # pasted keys still override minting
    code, data = post("/api/install", {
        "custom": True, "service": "pastedkey",
        "image": "docker.io/alpine:latest",
        "authkey": "dummy-test-authkey-pasted"})
    pastedfile = os.path.join(pods, "pastedkey", ".tailscale_authkey")
    check(code == 200 and data["ok"]
          and open(pastedfile).read().strip() == "dummy-test-authkey-pasted",
          "a pasted key overrides auto-minting")
    check(os.stat(pastedfile).st_mode & 0o777 == 0o600,
          "pasted key file is 0600")
finally:
    app._ts_token = _real_ts_token
    app.ts_api = _real_ts_api
    app.ts_policy_sync = _real_policy_sync

# --- wizard save: stub the live probe, expect a 0600 whitelisted file ---
_real_validate = app.op_tsapi_validate
app.op_tsapi_validate = lambda data: {
    "ok": True, "mode": "token",
    "checks": {k: {"ok": True, "detail": None}
               for k in ("devices", "auth_keys", "policy_file")},
    "fences": {"present": list(app.FENCE_SECTIONS), "missing": []},
    "error": None}
try:
    code, data = post("/api/tsapi", {"token": "dummy-test-authkey-tsapi",
                                     "junk": "must-not-persist"})
    check(code == 200 and data["ok"] and data["saved"],
          "POST /api/tsapi validates then saves")
    saved = json.load(open(os.path.join(pods, ".tsapi.json")))
    check(saved == {"token": "dummy-test-authkey-tsapi"},
          ".tsapi.json holds exactly the whitelisted credential fields")
    check(os.stat(os.path.join(pods, ".tsapi.json")).st_mode & 0o777 == 0o600,
          ".tsapi.json is 0600")
    code, data = get("/api/tsapi")
    check(code == 200 and data["configured"] and data["mode"] == "token",
          "GET /api/tsapi reports the saved credential")
finally:
    app.op_tsapi_validate = _real_validate
    os.remove(os.path.join(pods, ".tsapi.json"))  # keep later tests offline

# --- catalog sources: add a URL source, merge, install from it, delete ---
code, data = post("/api/sources", {"do": "add", "name": "community", "url": CAT_URL})
check(code == 200 and data["ok"] and "1 services" in (data.get("message") or ""),
      "POST /api/sources add fetches + validates the catalog")
code, data = get("/api/sources")
check(any(s["name"] == "community" and s["service_count"] == 1 and not s["error"]
          for s in data["sources"]),
      "GET /api/sources lists it with a service count")
code, data = get("/api/catalog")
ext = [c for c in data["catalog"] if c["name"] == "extpod"]
check(bool(ext) and ext[0]["source"] == "community",
      "source service merged into the catalog, tagged with its source")
code, data = post("/api/install", {"service": "extpod", "volumes": {},
                                    "authkey": "dummy-test-authkey-api"})
check(code == 200 and data["ok"], "install a service that came from a source")
check(app.pod_config("extpod")["image"] == "docker.io/alpine:latest",
      "source service resolved from the merged catalog and installed")
code, data = post("/api/sources", {"do": "add", "name": "bad", "url": "ftp://nope"})
check(code == 400 and "http" in data["error"], "reject a non-http(s) source URL")
code, data = post("/api/sources", {"do": "delete", "name": "community"})
check(code == 200 and data["ok"], "delete source")
code, data = get("/api/catalog")
check(not any(c["name"] == "extpod" for c in data["catalog"]),
      "source's services leave the catalog after the source is deleted")

catsrv.shutdown()
srv.shutdown()
print("WEB API TEST PASSED")
