#!/usr/bin/env python3
"""Podscale web UI - concept-validation MVP.

Deliberately basic: Python stdlib only, no styling, no auth (it is reachable
only over the tailnet). A thin front end over the same engine the CLI wizard
uses: it builds the config JSON and pipes it to create.sh, and start/stop
just invoke each pod's generated run.sh/stop.sh.

Expects (provided by the container image / bootstrap script):
  - engine scripts + homelab.js in APP_DIR
  - host ~/Pods mounted at PODS_DIR (same path as on the host!)
  - host podman socket mounted, CONTAINER_HOST pointing at it
"""

import html
import json
import os
import subprocess
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_DIR = os.environ.get("APP_DIR", "/app")
PODS_DIR = os.environ.get("PODS_DIR", "/root/Pods")
PORT = int(os.environ.get("PORT", "8080"))

CONTROLLER_PODS = {"homepod"}  # don't offer stop-self buttons

# Shared media folders (the only thing allowed to pierce the pod barrier).
# Each share: {"host_path": "/data", "container_path": "/data", "ro": false}
SHARES_FILE = os.path.join(PODS_DIR, ".shares.json")


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


def page(title, body):
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title></head>"
        f"<body><h1>{html.escape(title)}</h1>{body}"
        "<hr><p><a href='/'>home</a></p></body></html>"
    ).encode()


def dashboard():
    services = load_services()
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
    for name, spec in sorted(services.items()):
        port = next(iter(spec.get("ports", {})), "")
        installed = " (installed)" if name in deployed else ""
        cat_rows.append(
            f"<tr><td>{html.escape(name)}{installed}</td>"
            f"<td>{html.escape(spec['image'])}</td><td>{port}</td>"
            f"<td><a href='/install?service={urllib.parse.quote(name)}'>install</a></td></tr>"
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


def shares_page(msg=""):
    shares = load_shares()
    deployed = deployed_services()

    usage = {}
    for pod in deployed:
        info = pod_config(pod) or {}
        for sname in info.get("shares", []):
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


def do_shares(form):
    import re
    action = form.get("do", [""])[0]
    shares = load_shares()

    if action == "add":
        name = form.get("name", [""])[0].strip()
        host = form.get("host_path", [""])[0].strip()
        cont = form.get("container_path", [""])[0].strip() or host
        host = host.rstrip("/") or "/"
        cont = cont.rstrip("/") or "/"
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
            return shares_page("Invalid name (a-z, 0-9, dashes).")
        if name in shares:
            return shares_page(f"Share '{name}' already exists.")
        if not host.startswith("/") or host.endswith(":ro"):
            return shares_page(
                "Host path must be absolute (use the checkbox for read-only)."
            )
        if not cont.startswith("/"):
            return shares_page("Container path must be absolute.")
        shares[name] = {
            "host_path": host,
            "container_path": cont,
            "ro": "ro" in form,
        }
        save_shares(shares)
        return shares_page(f"Added share '{name}'.")

    if action == "delete":
        name = form.get("name", [""])[0]
        if shares.pop(name, None) is None:
            return shares_page("Unknown share.")
        save_shares(shares)
        return shares_page(
            f"Deleted share '{name}'. Pods that mount it keep their volume"
            " until re-rendered."
        )

    if action == "attach":
        return do_attach(form, shares)

    return shares_page("Unknown action.")


def do_attach(form, shares):
    pod = form.get("pod", [""])[0]
    sname = form.get("share", [""])[0]
    share = shares.get(sname)
    if not share or pod not in deployed_services() or pod in CONTROLLER_PODS:
        return shares_page("Unknown pod or share.")
    info = pod_config(pod)
    if not info:
        return shares_page(
            f"No readable .config.json for {pod} (redeploy once to create it)."
        )
    if sname in info.get("shares", []):
        return shares_page(f"'{sname}' is already attached to {pod}.")
    cpath, host = share_volume(share)
    if cpath in info.get("volumes", {}):
        return shares_page(f"{pod} already mounts something at {cpath}.")

    config = config_from_info(info)
    config["volumes"][cpath] = host
    config["shares"] = sorted(config["shares"] + [sname])
    result = run_create(config)
    out = html.escape(result.stdout + result.stderr)
    if result.returncode != 0:
        return page(f"attach {sname} to {pod}: FAILED", f"<pre>{out}</pre>")

    restart_button = (
        f"<form method='post' action='/action'>"
        f"<input type='hidden' name='service' value='{html.escape(pod)}'>"
        f"<button name='do' value='start'>Restart {html.escape(pod)} now</button>"
        f"</form>"
        "<p>Scripts regenerated with the new mount - the running pod is"
        " untouched until restarted.</p>"
    )
    return page(f"attach {sname} to {pod}: ok", restart_button + f"<pre>{out}</pre>")


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
    name = form.get("service", [""])[0].strip()
    if "custom" in form:
        import re
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
            return page("Error", "<p>Invalid name (a-z, 0-9, dashes).</p>")
        spec = parse_custom_spec(form, name)
        if not spec["image"]:
            return page("Error", "<p>An image is required.</p>")
    else:
        spec = load_services().get(name)
    if not spec:
        return page("Error", "<p>Unknown service.</p>")

    tailscale = "yes" if "tailscale" in form else "no"
    npm = "yes" if "npm" in form else "no"
    https = "yes" if ("https" in form and tailscale == "yes") else "no"

    auth_key_file = ""
    if tailscale == "yes":
        auth_key_file = os.path.join(PODS_DIR, name, ".tailscale_authkey")
        pasted = form.get("authkey", [""])[0].strip()
        if pasted:
            os.makedirs(os.path.dirname(auth_key_file), exist_ok=True)
            with open(auth_key_file, "w") as f:
                f.write(pasted + "\n")
            os.chmod(auth_key_file, 0o600)
        elif not os.path.isfile(auth_key_file):
            return page("Error", "<p>Tailscale enabled but no auth key given.</p>")

    if "custom" in form:
        env = spec["environment"]
        volumes = spec["volumes"]
    else:
        env = {
            k[len("env."):]: v[0]
            for k, v in form.items()
            if k.startswith("env.")
        }
        volumes = {
            k[len("vol."):]: v[0]  # container path -> host path (engine order)
            for k, v in form.items()
            if k.startswith("vol.")
        }

    shares = load_shares()
    attached = []
    for key in form:
        if key.startswith("share."):
            share = shares.get(key[len("share."):])
            if share:
                cpath, host = share_volume(share)
                volumes[cpath] = host
                attached.append(key[len("share."):])

    network_mode = (
        f"service:tailscale-{name}" if tailscale == "yes"
        else spec.get("network_mode", "bridge")
    )
    config = {
        "container": name,
        "image": spec["image"],
        "network_mode": network_mode,
        "ports": spec.get("ports", {}),
        "restart_policy": spec.get("restart_policy", "unless-stopped"),
        "include_npm": npm,
        "include_tailscale": tailscale,
        "include_https": https,
        "auth_key_file": auth_key_file,
        "base_path": PODS_DIR,
        "environment": env,
        "volumes": volumes,
        "command": spec.get("command", ""),
        "shares": sorted(attached),
    }

    result = run_create(config)
    out = html.escape(result.stdout + result.stderr)
    if result.returncode != 0:
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
    if name not in deployed_services():
        return page("Error", "<p>Unknown service.</p>")
    if name in CONTROLLER_PODS and action == "stop":
        return page("Refused", "<p>Not stopping the controller from itself.</p>")

    svc_dir = os.path.join(PODS_DIR, name)
    if action == "start":
        r = subprocess.run(
            ["sh", "./run.sh"], cwd=svc_dir, capture_output=True, text=True,
            timeout=600,
        )
    elif action == "stop":
        r = subprocess.run(
            ["sh", "./stop.sh"], cwd=svc_dir, capture_output=True, text=True,
            timeout=120,
        )
    elif action == "logs":
        r = podman("logs", "--tail", "100", name, timeout=30)
    elif action == "update":
        # Pull the current image tag, then recreate the pod from run.sh.
        cfg_path = os.path.join(svc_dir, ".config.json")
        try:
            image = json.load(open(cfg_path))["image"]
        except (OSError, ValueError, KeyError):
            return page("Error", "<p>No .config.json for this pod (redeploy once to create it).</p>")
        pull = podman("pull", image, timeout=600)
        if pull.returncode != 0:
            return page(f"update {name}: pull failed",
                        f"<pre>{html.escape(pull.stdout + pull.stderr)}</pre>")
        r = subprocess.run(
            ["sh", "./run.sh"], cwd=svc_dir, capture_output=True, text=True,
            timeout=600,
        )
    else:
        return page("Error", "<p>Unknown action.</p>")

    out = html.escape(r.stdout + r.stderr)
    status = "ok" if r.returncode == 0 else f"exit {r.returncode}"
    return page(f"{action} {name}: {status}", f"<pre>{out}</pre>")


class Handler(BaseHTTPRequestHandler):
    def _send(self, content, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
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
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        try:
            if self.path == "/install":
                self._send(do_install(form))
            elif self.path == "/action":
                self._send(do_action(form))
            elif self.path == "/shares":
                self._send(do_shares(form))
            else:
                self._send(page("Not found", ""), 404)
        except subprocess.TimeoutExpired:
            self._send(page("Timeout", "<p>The operation took too long.</p>"), 500)

    def log_message(self, fmt, *args):  # quieter default logging
        print("%s - %s" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    print(f"Podscale web UI on :{PORT} (pods dir: {PODS_DIR})")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
