#!/usr/bin/env python3
"""Podscale web controller.

Architecture (Phase 1 of the robust-UI rebuild):

  * op_*()      -- pure logic. Take plain data, talk to the create.sh engine
                   and podman, and return structured result dicts. No HTML.
  * JSON API    -- /api/* endpoints. Thin adapters that (de)serialize JSON
                   around the op_* functions. This is what the React SPA
                   (Phases 2-3) consumes.
  * Static SPA  -- files under STATIC_DIR are served at the web root, with an
                   index.html fallback for client-side routing. Populated by
                   the CI build in a later phase; absent today.
  * Legacy HTML -- the deliberately-lean MVP UI, kept working by delegating to
                   the same op_* functions. Served only while STATIC_DIR has no
                   build. Removed once the SPA lands.

Still stdlib-only and no-auth (reachable only over the tailnet by design).

Expects (provided by the container image / bootstrap script):
  - engine scripts + homelab.js in APP_DIR
  - host ~/Pods mounted at PODS_DIR (same path as on the host!)
  - host podman socket mounted, CONTAINER_HOST pointing at it
"""

import html
import json
import mimetypes
import os
import re
import subprocess
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_DIR = os.environ.get("APP_DIR", "/app")
PODS_DIR = os.environ.get("PODS_DIR", "/root/Pods")
STATIC_DIR = os.environ.get("STATIC_DIR", os.path.join(APP_DIR, "static"))
PORT = int(os.environ.get("PORT", "8080"))

CONTROLLER_PODS = {"podscale", "homepod"}  # don't offer stop-self buttons ("homepod" = pre-rename deploys)

# Shared media folders (the only thing allowed to pierce the pod barrier).
# Each share: {"host_path": "/data", "container_path": "/data", "ro": false}
SHARES_FILE = os.path.join(PODS_DIR, ".shares.json")

NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


# =========================================================================
# Data helpers (filesystem + podman + engine)
# =========================================================================
def load_services():
    with open(os.path.join(APP_DIR, "homelab.js")) as f:
        return {s["name"]: s for s in json.load(f)}


def load_shares():
    try:
        with open(SHARES_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_shares(shares):
    tmp = SHARES_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(shares, f, indent=2)
    os.replace(tmp, SHARES_FILE)


def share_volume(share):
    """Volume entry (container_path, host_path[:ro]) for a share."""
    host = share["host_path"] + (":ro" if share.get("ro") else "")
    return share["container_path"], host


def pod_config(name):
    try:
        with open(os.path.join(PODS_DIR, name, ".config.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def podman(*args, timeout=60):
    try:
        return subprocess.run(
            ["podman", *args], capture_output=True, text=True, timeout=timeout
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(args, 1, "", f"podman unavailable: {e}")


def running_names():
    out = podman("ps", "--format", "{{.Names}}")
    return set(out.stdout.split()) if out.returncode == 0 else set()


def deployed_services():
    if not os.path.isdir(PODS_DIR):
        return []
    return sorted(
        d
        for d in os.listdir(PODS_DIR)
        if os.path.isfile(os.path.join(PODS_DIR, d, "run.sh"))
    )


def config_from_info(info):
    """Rebuild a create.sh input config from a pod's saved .config.json."""
    return {
        "container": info["service"],
        "image": info["image"],
        "network_mode": info.get("network_mode", "bridge"),
        "ports": info.get("ports", {}),
        "restart_policy": info.get("restart_policy", "unless-stopped"),
        "include_npm": info.get("include_npm", "no"),
        "include_tailscale": info.get("include_tailscale", "no"),
        "include_https": info.get("include_https", "no"),
        "auth_key_file": info.get("auth_key_file", ""),
        "base_path": info.get("base_path", PODS_DIR),
        "environment": info.get("environment", {}),
        "volumes": info.get("volumes", {}),
        "command": info.get("command", ""),
        "memory_limit": info.get("memory_limit", ""),
        "shares": info.get("shares", []),
    }


def run_create(config):
    return subprocess.run(
        ["bash", os.path.join(APP_DIR, "create.sh")],
        input=json.dumps(config),
        capture_output=True,
        text=True,
        cwd="/tmp",
        timeout=300,
    )


# =========================================================================
# Core operations -- pure logic returning result dicts (no HTML)
# =========================================================================
def status_pods():
    """List deployed pods with their runtime state and saved metadata."""
    running = running_names()
    out = []
    for name in deployed_services():
        info = pod_config(name) or {}
        out.append({
            "name": name,
            "state": "running" if name in running else "stopped",
            "controller": name in CONTROLLER_PODS,
            "image": info.get("image", ""),
            "tailscale": info.get("include_tailscale") == "yes",
            "https": info.get("include_https") == "yes",
            "shares": info.get("shares", []),
        })
    return out


def status_catalog():
    """The installable service catalog, flagged with what's deployed."""
    deployed = set(deployed_services())
    out = []
    for name, spec in sorted(load_services().items()):
        out.append({
            "name": name,
            "image": spec["image"],
            "ports": spec.get("ports", {}),
            "port": next(iter(spec.get("ports", {})), ""),
            "environment": spec.get("environment", {}),
            "volumes": spec.get("volumes", {}),
            "command": spec.get("command", ""),
            "installed": name in deployed,
        })
    return out


def status_shares():
    """Defined shares, each with mode/visibility and the pods using it."""
    shares = load_shares()
    usage = {}
    for pod in deployed_services():
        for sname in (pod_config(pod) or {}).get("shares", []):
            usage.setdefault(sname, []).append(pod)
    out = []
    for name, s in sorted(shares.items()):
        out.append({
            "name": name,
            "host_path": s["host_path"],
            "container_path": s["container_path"],
            "ro": bool(s.get("ro")),
            "mode": "read-only" if s.get("ro") else "read-write",
            "visible": os.path.isdir(s["host_path"]),
            "used_by": usage.get(name, []),
        })
    return out


def op_install(req):
    """Generate a pod from an install request.

    req: name, custom(bool), image, command, ports, environment, volumes,
         shares(list of names), tailscale(bool), https(bool), npm(bool),
         authkey, network_mode, restart_policy.
    Returns {ok, name, error, output}. error set => rejected before the engine;
    ok False with output set => create.sh failed.
    """
    name = (req.get("name") or "").strip()
    custom = bool(req.get("custom"))
    image = (req.get("image") or "").strip()

    if custom:
        if not NAME_RE.fullmatch(name):
            return {"ok": False, "name": name, "error": "Invalid name (a-z, 0-9, dashes).", "output": ""}
        if not image:
            return {"ok": False, "name": name, "error": "An image is required.", "output": ""}

    tailscale = bool(req.get("tailscale"))
    npm = bool(req.get("npm"))
    https = bool(req.get("https")) and tailscale

    auth_key_file = ""
    if tailscale:
        auth_key_file = os.path.join(PODS_DIR, name, ".tailscale_authkey")
        pasted = (req.get("authkey") or "").strip()
        if pasted:
            os.makedirs(os.path.dirname(auth_key_file), exist_ok=True)
            with open(auth_key_file, "w") as f:
                f.write(pasted + "\n")
            os.chmod(auth_key_file, 0o600)
        elif not os.path.isfile(auth_key_file):
            return {"ok": False, "name": name, "error": "Tailscale enabled but no auth key given.", "output": ""}

    volumes = dict(req.get("volumes") or {})
    reg = load_shares()
    attached = []
    for sname in req.get("shares") or []:
        share = reg.get(sname)
        if share:
            cpath, host = share_volume(share)
            volumes[cpath] = host
            attached.append(sname)

    network_mode = (
        f"service:tailscale-{name}" if tailscale
        else req.get("network_mode", "bridge")
    )
    config = {
        "container": name,
        "image": image,
        "network_mode": network_mode,
        "ports": req.get("ports") or {},
        "restart_policy": req.get("restart_policy", "unless-stopped"),
        "include_npm": "yes" if npm else "no",
        "include_tailscale": "yes" if tailscale else "no",
        "include_https": "yes" if https else "no",
        "auth_key_file": auth_key_file,
        "base_path": PODS_DIR,
        "environment": req.get("environment") or {},
        "volumes": volumes,
        "command": req.get("command", ""),
        "shares": sorted(attached),
    }
    result = run_create(config)
    output = result.stdout + result.stderr
    if result.returncode != 0:
        return {"ok": False, "name": name, "error": None, "output": output}
    return {"ok": True, "name": name, "error": None, "output": output}


def op_action(name, action):
    """start / stop / logs / update a deployed pod. Returns a result dict."""
    if name not in deployed_services():
        return {"ok": False, "name": name, "action": action, "status": "error",
                "error": "Unknown service.", "output": ""}
    if name in CONTROLLER_PODS and action == "stop":
        return {"ok": False, "name": name, "action": action, "status": "refused",
                "error": "Not stopping the controller from itself.", "output": ""}

    svc_dir = os.path.join(PODS_DIR, name)
    if action == "start":
        r = subprocess.run(["sh", "./run.sh"], cwd=svc_dir, capture_output=True,
                           text=True, timeout=600)
    elif action == "stop":
        r = subprocess.run(["sh", "./stop.sh"], cwd=svc_dir, capture_output=True,
                           text=True, timeout=120)
    elif action == "logs":
        r = podman("logs", "--tail", "100", name, timeout=30)
    elif action == "update":
        # Pull the current image tag, then recreate the pod from run.sh.
        info = pod_config(name)
        if not info or "image" not in info:
            return {"ok": False, "name": name, "action": action, "status": "error",
                    "error": "No .config.json for this pod (redeploy once to create it).",
                    "output": ""}
        pull = podman("pull", info["image"], timeout=600)
        if pull.returncode != 0:
            return {"ok": False, "name": name, "action": action, "status": "pull failed",
                    "error": "pull failed", "output": pull.stdout + pull.stderr}
        r = subprocess.run(["sh", "./run.sh"], cwd=svc_dir, capture_output=True,
                           text=True, timeout=600)
    else:
        return {"ok": False, "name": name, "action": action, "status": "error",
                "error": "Unknown action.", "output": ""}

    output = r.stdout + r.stderr
    ok = r.returncode == 0
    return {"ok": ok, "name": name, "action": action,
            "status": "ok" if ok else f"exit {r.returncode}",
            "error": None, "output": output}


def op_share_add(name, host_path, container_path, ro):
    """Add a share to the registry. Returns a result dict."""
    shares = load_shares()
    name = (name or "").strip()
    raw_host = (host_path or "").strip()
    cont = (container_path or "").strip() or raw_host
    host = raw_host.rstrip("/") or "/"
    cont = cont.rstrip("/") or "/"

    if not NAME_RE.fullmatch(name):
        return {"ok": False, "name": name, "error": "Invalid name (a-z, 0-9, dashes)."}
    if name in shares:
        return {"ok": False, "name": name, "error": f"Share '{name}' already exists."}
    if not host.startswith("/") or host.endswith(":ro"):
        return {"ok": False, "name": name,
                "error": "Host path must be absolute (use the checkbox for read-only)."}
    if not cont.startswith("/"):
        return {"ok": False, "name": name, "error": "Container path must be absolute."}

    shares[name] = {"host_path": host, "container_path": cont, "ro": bool(ro)}
    save_shares(shares)
    return {"ok": True, "name": name, "error": None,
            "message": f"Added share '{name}'.", "share": shares[name]}


def op_share_delete(name):
    shares = load_shares()
    if shares.pop(name, None) is None:
        return {"ok": False, "name": name, "error": "Unknown share."}
    save_shares(shares)
    return {"ok": True, "name": name, "error": None,
            "message": f"Deleted share '{name}'. Pods that mount it keep their volume"
                       " until re-rendered."}


def op_attach(pod, sname):
    """Attach a share to an already-deployed pod. Returns a result dict."""
    shares = load_shares()
    share = shares.get(sname)
    if not share or pod not in deployed_services() or pod in CONTROLLER_PODS:
        return {"ok": False, "pod": pod, "share": sname, "error": "Unknown pod or share.",
                "output": ""}
    info = pod_config(pod)
    if not info:
        return {"ok": False, "pod": pod, "share": sname, "output": "",
                "error": f"No readable .config.json for {pod} (redeploy once to create it)."}
    if sname in info.get("shares", []):
        return {"ok": False, "pod": pod, "share": sname, "output": "",
                "error": f"'{sname}' is already attached to {pod}."}
    cpath, host = share_volume(share)
    if cpath in info.get("volumes", {}):
        return {"ok": False, "pod": pod, "share": sname, "output": "",
                "error": f"{pod} already mounts something at {cpath}."}

    config = config_from_info(info)
    config["volumes"][cpath] = host
    config["shares"] = sorted(config["shares"] + [sname])
    result = run_create(config)
    output = result.stdout + result.stderr
    if result.returncode != 0:
        return {"ok": False, "pod": pod, "share": sname, "output": output,
                "error": f"attach {sname} to {pod}: FAILED"}
    return {"ok": True, "pod": pod, "share": sname, "output": output, "error": None,
            "message": f"attach {sname} to {pod}: ok"}


# =========================================================================
# JSON API
# =========================================================================
def api_get(path):
    if path == "/api/pods":
        return 200, {"pods": status_pods()}
    if path == "/api/catalog":
        return 200, {"catalog": status_catalog()}
    if path == "/api/shares":
        return 200, {"shares": status_shares()}
    m = re.fullmatch(r"/api/pods/([a-z0-9][a-z0-9-]*)/logs", path)
    if m:
        return 200, op_action(m.group(1), "logs")
    return 404, {"error": "not found"}


def _install_req_from_json(data):
    """Build an op_install request from a JSON API payload."""
    name = (data.get("service") or data.get("name") or "").strip()
    if data.get("custom"):
        return {
            "name": name, "custom": True,
            "image": data.get("image", ""), "command": data.get("command", ""),
            "ports": data.get("ports", {}), "environment": data.get("environment", {}),
            "volumes": data.get("volumes", {}),
            "network_mode": "bridge", "restart_policy": "unless-stopped",
            "shares": data.get("shares", []),
            "tailscale": bool(data.get("tailscale", True)),
            "https": bool(data.get("https", True)),
            "npm": bool(data.get("npm", False)),
            "authkey": data.get("authkey", ""),
        }, None
    spec = load_services().get(name)
    if not spec:
        return None, "Unknown service."
    volumes = data.get("volumes")
    if volumes is None:
        volumes = {
            cpath: os.path.join(PODS_DIR, name, cpath.lstrip("/"))
            for _, cpath in spec.get("volumes", {}).items()
        }
    return {
        "name": name, "custom": False,
        "image": spec["image"], "command": spec.get("command", ""),
        "ports": data.get("ports", spec.get("ports", {})),
        "environment": {**spec.get("environment", {}), **data.get("environment", {})},
        "volumes": volumes,
        "network_mode": spec.get("network_mode", "bridge"),
        "restart_policy": spec.get("restart_policy", "unless-stopped"),
        "shares": data.get("shares", []),
        "tailscale": bool(data.get("tailscale", True)),
        "https": bool(data.get("https", True)),
        "npm": bool(data.get("npm", False)),
        "authkey": data.get("authkey", ""),
    }, None


def api_post(path, data):
    if path == "/api/install":
        req, err = _install_req_from_json(data)
        if err:
            return 400, {"ok": False, "error": err}
        result = op_install(req)
        code = 200 if result["ok"] else (400 if result.get("error") else 500)
        return code, result

    m = re.fullmatch(r"/api/pods/([a-z0-9][a-z0-9-]*)/action", path)
    if m:
        result = op_action(m.group(1), (data.get("do") or "").strip())
        return (200 if result["ok"] else 400), result

    if path == "/api/shares":
        action = (data.get("do") or "").strip()
        if action == "add":
            result = op_share_add(data.get("name"), data.get("host_path"),
                                  data.get("container_path"), data.get("ro"))
        elif action == "delete":
            result = op_share_delete(data.get("name"))
        elif action == "attach":
            result = op_attach(data.get("pod"), data.get("share"))
        else:
            return 400, {"ok": False, "error": "Unknown action."}
        return (200 if result["ok"] else 400), result

    return 404, {"error": "not found"}


# =========================================================================
# Legacy HTML UI (delegates to op_* -- retired when the SPA ships)
# =========================================================================
def page(title, body):
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title></head>"
        f"<body><h1>{html.escape(title)}</h1>{body}"
        "<hr><p><a href='/'>home</a></p></body></html>"
    ).encode()


def dashboard():
    running = running_names()
    deployed = deployed_services()

    rows = []
    for name in deployed:
        state = "running" if name in running else "stopped"
        buttons = (
            f"<form style='display:inline' method='post' action='/action'>"
            f"<input type='hidden' name='service' value='{html.escape(name)}'>"
            f"<button name='do' value='start'>start</button> "
            f"<button name='do' value='stop'>stop</button> "
            f"<button name='do' value='logs'>logs</button> "
            f"<button name='do' value='update'>update</button></form>"
        )
        rows.append(
            f"<tr><td>{html.escape(name)}</td><td>{state}</td><td>{buttons}</td></tr>"
        )
    deployed_html = (
        "<table border=1><tr><th>service</th><th>state</th><th>actions</th></tr>"
        + "".join(rows)
        + "</table>"
        if rows
        else "<p>No services deployed yet.</p>"
    )

    cat_rows = []
    for spec in status_catalog():
        installed = " (installed)" if spec["installed"] else ""
        cat_rows.append(
            f"<tr><td>{html.escape(spec['name'])}{installed}</td>"
            f"<td>{html.escape(spec['image'])}</td><td>{spec['port']}</td>"
            f"<td><a href='/install?service={urllib.parse.quote(spec['name'])}'>install</a></td></tr>"
        )
    catalog_html = (
        "<table border=1><tr><th>service</th><th>image</th><th>port</th><th></th></tr>"
        + "".join(cat_rows)
        + "</table>"
    )

    return page(
        "Podscale",
        f"<h2>Deployed</h2>{deployed_html}<h2>Catalog</h2>{catalog_html}"
        "<p><a href='/custom'>+ Custom pod</a> (any OCI image) | "
        "<a href='/shares'>Shared folders</a></p>",
    )


def parse_custom_spec(form, name):
    ports = {}
    for line in form.get("ports", [""])[0].splitlines():
        line = line.strip()
        if ":" in line:
            host, _, cont = line.partition(":")
            ports[host.strip()] = cont.strip()
    env = {}
    for line in form.get("envlines", [""])[0].splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    volumes = {}
    for line in form.get("vollines", [""])[0].splitlines():
        if "=" in line:
            cpath, _, hpath = line.partition("=")
            cpath, hpath = cpath.strip(), hpath.strip()
            if cpath.startswith("/") and hpath.startswith("/"):
                volumes[cpath] = hpath
    return {
        "name": name,
        "image": form.get("image", [""])[0].strip(),
        "network_mode": "bridge",
        "restart_policy": "unless-stopped",
        "ports": ports,
        "environment": env,
        "volumes": volumes,
        "command": form.get("command", [""])[0].strip(),
    }


def share_checkboxes():
    shares = load_shares()
    if not shares:
        return "<p>none defined - <a href='/shares'>add shared folders</a></p>"
    boxes = []
    for name, s in sorted(shares.items()):
        cpath, host = share_volume(s)
        boxes.append(
            f"<label><input type='checkbox' name='share.{html.escape(name)}'> "
            f"{html.escape(name)} ({html.escape(host)} &rarr; {html.escape(cpath)})"
            f"</label><br>"
        )
    return "".join(boxes)


def custom_form():
    body = f"""
<form method='post' action='/install'>
<input type='hidden' name='custom' value='1'>
<p><label>Name (a-z, 0-9, dashes) <input name='service' required></label></p>
<p><label>Image <input size=60 name='image' required
placeholder='ghcr.io/someone/thing:latest'></label></p>
<p><label>Command (optional) <input size=40 name='command'
placeholder='e.g. sleep infinity'></label></p>
<p><label>Ports, one host:container per line<br>
<textarea name='ports' rows=2 cols=30 placeholder='8080:8080'></textarea></label></p>
<p><label>Environment, one KEY=value per line<br>
<textarea name='envlines' rows=3 cols=40></textarea></label></p>
<p><label>Volumes, one /container/path=/host/path per line (append :ro to a host path for read-only)<br>
<textarea name='vollines' rows=3 cols=60
placeholder='/config={html.escape(PODS_DIR)}/&lt;name&gt;/config'></textarea></label></p>
<h3>Shared folders</h3>
{share_checkboxes()}
<p><label><input type='checkbox' name='tailscale' checked> Tailscale (own tailnet identity)</label></p>
<p><label><input type='checkbox' name='https' checked> HTTPS via tailscale serve (first port)</label></p>
<p><label>Tailscale auth key <input size=70 name='authkey' autocomplete='off'></label></p>
<p><button>Install</button></p>
</form>"""
    return page("Custom pod", body)


def shares_page(msg=""):
    shares = load_shares()
    deployed = deployed_services()

    usage = {}
    for pod in deployed:
        for sname in (pod_config(pod) or {}).get("shares", []):
            usage.setdefault(sname, []).append(pod)

    rows = []
    for name, s in sorted(shares.items()):
        mode = "read-only" if s.get("ro") else "read-write"
        visible = "yes" if os.path.isdir(s["host_path"]) else "no"
        used = ", ".join(usage.get(name, [])) or "-"
        rows.append(
            f"<tr><td>{html.escape(name)}</td><td>{html.escape(s['host_path'])}</td>"
            f"<td>{html.escape(s['container_path'])}</td><td>{mode}</td>"
            f"<td>{visible}</td><td>{html.escape(used)}</td>"
            f"<td><form style='display:inline' method='post' action='/shares'>"
            f"<input type='hidden' name='name' value='{html.escape(name)}'>"
            f"<button name='do' value='delete'>delete</button></form></td></tr>"
        )
    table = (
        "<table border=1><tr><th>name</th><th>host path</th><th>container path</th>"
        "<th>mode</th><th>visible</th><th>used by</th><th></th></tr>"
        + "".join(rows) + "</table>"
        "<p><small>'visible' is checked from inside the controller, which only"
        " mounts the Pods dir - a path can exist on the pod host and still show"
        " 'no' here. Pods mount host paths directly, so 'no' does not block"
        " anything.</small></p>"
        if rows
        else "<p>No shared folders defined yet.</p>"
    )

    pod_opts = "".join(
        f"<option>{html.escape(p)}</option>"
        for p in deployed if p not in CONTROLLER_PODS
    )
    share_opts = "".join(f"<option>{html.escape(n)}</option>" for n in sorted(shares))
    attach_html = (
        f"<h2>Attach to a deployed pod</h2>"
        f"<form method='post' action='/shares'>"
        f"<label>share <select name='share'>{share_opts}</select></label> "
        f"<label>pod <select name='pod'>{pod_opts}</select></label> "
        f"<button name='do' value='attach'>attach</button></form>"
        "<p><small>Attaching regenerates the pod's scripts; restart the pod to"
        " apply. New pods can attach shares directly on the install forms."
        "</small></p>"
        if shares and pod_opts
        else ""
    )

    add_html = f"""
<h2>Add a shared folder</h2>
<form method='post' action='/shares'>
<p><label>Name (a-z, 0-9, dashes) <input name='name' required
placeholder='media'></label></p>
<p><label>Host path <input size=40 name='host_path' required
placeholder='/data'></label></p>
<p><label>Container path (blank = same as host path)
<input size=40 name='container_path' placeholder='/data'></label></p>
<p><label><input type='checkbox' name='ro'> Read-only</label></p>
<p><button name='do' value='add'>Add</button></p>
</form>
<p><small>Shared folders are for media only - configs and databases belong to
each pod under {html.escape(PODS_DIR)}. Keep downloads and media on the same
share so imports can hardlink.</small></p>"""

    msg_html = f"<p><b>{html.escape(msg)}</b></p>" if msg else ""
    return page("Shared folders", msg_html + table + attach_html + add_html)


def install_form(name):
    spec = load_services().get(name)
    if not spec:
        return page("Unknown service", "<p>Not in catalog.</p>")

    env_fields = "".join(
        f"<label>{html.escape(k)} "
        f"<input name='env.{html.escape(k)}' value='{html.escape(v)}'></label><br>"
        for k, v in spec.get("environment", {}).items()
    )
    vol_fields = "".join(
        f"<label>host path for {html.escape(cpath)} "
        f"<input size=50 name='vol.{html.escape(cpath)}' "
        f"value='{html.escape(os.path.join(PODS_DIR, name, cpath.lstrip('/')))}'>"
        f"</label><br>"
        for _, cpath in spec.get("volumes", {}).items()
    )
    key_file = os.path.join(PODS_DIR, name, ".tailscale_authkey")
    key_hint = "existing key file found - leave blank to reuse it" if os.path.isfile(
        key_file
    ) else "paste a fresh single-use, non-ephemeral key"

    body = f"""
<form method='post' action='/install'>
<input type='hidden' name='service' value='{html.escape(name)}'>
<p><label><input type='checkbox' name='tailscale' checked> Tailscale (own tailnet identity)</label></p>
<p><label><input type='checkbox' name='https' checked> HTTPS via tailscale serve
(https://{html.escape(name)}.&lt;tailnet&gt;.ts.net - needs HTTPS Certificates
enabled once in the Tailscale admin console)</label></p>
<p><label><input type='checkbox' name='npm'> Bundle Nginx Proxy Manager</label></p>
<p><label>Tailscale auth key ({key_hint})<br>
<input size=70 name='authkey' autocomplete='off'></label></p>
<h3>Environment</h3>{env_fields or "<p>none</p>"}
<h3>Volumes</h3>{vol_fields or "<p>none</p>"}
<h3>Shared folders</h3>{share_checkboxes()}
<p><button>Install</button></p>
</form>"""
    return page(f"Install {name}", body)


def do_install(form):
    """Legacy HTML install: parse the flat form into an op_install request."""
    name = form.get("service", [""])[0].strip()
    if "custom" in form:
        spec = parse_custom_spec(form, name)
        req = {
            "name": name, "custom": True,
            "image": spec["image"], "command": spec["command"],
            "ports": spec["ports"], "environment": spec["environment"],
            "volumes": spec["volumes"],
            "network_mode": spec["network_mode"], "restart_policy": spec["restart_policy"],
        }
    else:
        spec = load_services().get(name)
        if not spec:
            return page("Error", "<p>Unknown service.</p>")
        req = {
            "name": name, "custom": False,
            "image": spec["image"], "command": spec.get("command", ""),
            "ports": spec.get("ports", {}),
            "environment": {k[len("env."):]: v[0] for k, v in form.items()
                            if k.startswith("env.")},
            "volumes": {k[len("vol."):]: v[0] for k, v in form.items()
                        if k.startswith("vol.")},
            "network_mode": spec.get("network_mode", "bridge"),
            "restart_policy": spec.get("restart_policy", "unless-stopped"),
        }
    req.update(
        shares=[k[len("share."):] for k in form if k.startswith("share.")],
        tailscale="tailscale" in form,
        https="https" in form,
        npm="npm" in form,
        authkey=form.get("authkey", [""])[0],
    )

    result = op_install(req)
    if result.get("error"):
        return page("Error", f"<p>{html.escape(result['error'])}</p>")
    out = html.escape(result["output"])
    if not result["ok"]:
        return page(f"Install {name}: FAILED", f"<pre>{out}</pre>")

    start_button = (
        f"<form method='post' action='/action'>"
        f"<input type='hidden' name='service' value='{html.escape(name)}'>"
        f"<button name='do' value='start'>Start {html.escape(name)} now</button>"
        f"</form>"
        "<p>Installing only generated the pod - it is not running until started."
        " Starting pulls the image and enrolls on the tailnet, so it can take"
        " a few minutes.</p>"
    )
    return page(f"Install {name}: installed", start_button + f"<pre>{out}</pre>")


def do_action(form):
    name = form.get("service", [""])[0]
    action = form.get("do", [""])[0]
    result = op_action(name, action)
    if result.get("error") and result["status"] in ("error", "refused"):
        title = "Refused" if result["status"] == "refused" else "Error"
        return page(title, f"<p>{html.escape(result['error'])}</p>")
    out = html.escape(result["output"])
    return page(f"{action} {name}: {result['status']}", f"<pre>{out}</pre>")


def do_shares(form):
    action = form.get("do", [""])[0]
    if action == "add":
        result = op_share_add(
            form.get("name", [""])[0], form.get("host_path", [""])[0],
            form.get("container_path", [""])[0], "ro" in form,
        )
        return shares_page(result.get("message") or result["error"])
    if action == "delete":
        result = op_share_delete(form.get("name", [""])[0])
        return shares_page(result.get("message") or result["error"])
    if action == "attach":
        return do_attach(form, load_shares())
    return shares_page("Unknown action.")


def do_attach(form, shares):
    pod = form.get("pod", [""])[0]
    sname = form.get("share", [""])[0]
    result = op_attach(pod, sname)
    if not result["ok"]:
        if result.get("output"):  # engine ran but failed
            return page(result["error"], f"<pre>{html.escape(result['output'])}</pre>")
        return shares_page(result["error"])

    restart_button = (
        f"<form method='post' action='/action'>"
        f"<input type='hidden' name='service' value='{html.escape(pod)}'>"
        f"<button name='do' value='start'>Restart {html.escape(pod)} now</button>"
        f"</form>"
        "<p>Scripts regenerated with the new mount - the running pod is"
        " untouched until restarted.</p>"
    )
    return page(f"attach {sname} to {pod}: ok",
                restart_button + f"<pre>{html.escape(result['output'])}</pre>")


# =========================================================================
# HTTP server
# =========================================================================
class Handler(BaseHTTPRequestHandler):
    def _send(self, content, code=200, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, obj, code=200):
        self._send(json.dumps(obj).encode(), code, "application/json")

    def serve_static(self, path):
        """Serve an SPA build from STATIC_DIR, with index.html routing fallback."""
        if not os.path.isdir(STATIC_DIR):
            return False
        base = os.path.realpath(STATIC_DIR)
        rel = urllib.parse.unquote(path).lstrip("/") or "index.html"
        full = os.path.realpath(os.path.join(base, rel))
        if full != base and not full.startswith(base + os.sep):
            return False  # path traversal attempt
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.isfile(full):
            # client-side route (no file extension) -> hand back index.html
            index = os.path.join(base, "index.html")
            if "." in os.path.basename(rel) or not os.path.isfile(index):
                return False
            full = index
        with open(full, "rb") as f:
            body = f.read()
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        self._send(body, 200, ctype)
        return True

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path.startswith("/api/"):
            code, obj = api_get(url.path)
            return self._send_json(obj, code)
        if self.serve_static(url.path):
            return
        # Legacy HTML UI (until an SPA build is present in STATIC_DIR)
        if url.path == "/":
            self._send(dashboard())
        elif url.path == "/install":
            q = urllib.parse.parse_qs(url.query)
            self._send(install_form(q.get("service", [""])[0]))
        elif url.path == "/custom":
            self._send(custom_form())
        elif url.path == "/shares":
            self._send(shares_page())
        else:
            self._send(page("Not found", ""), 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            if self.path.startswith("/api/"):
                data = json.loads(raw.decode() or "{}")
                code, obj = api_post(self.path, data)
                return self._send_json(obj, code)
            form = urllib.parse.parse_qs(raw.decode())
            if self.path == "/install":
                self._send(do_install(form))
            elif self.path == "/action":
                self._send(do_action(form))
            elif self.path == "/shares":
                self._send(do_shares(form))
            else:
                self._send(page("Not found", ""), 404)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON body"}, 400)
        except subprocess.TimeoutExpired:
            if self.path.startswith("/api/"):
                self._send_json({"error": "operation timed out"}, 504)
            else:
                self._send(page("Timeout", "<p>The operation took too long.</p>"), 500)

    def log_message(self, fmt, *args):  # quieter default logging
        print("%s - %s" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    print(f"Podscale web UI on :{PORT} (pods dir: {PODS_DIR})")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
