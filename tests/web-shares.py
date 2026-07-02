#!/usr/bin/env python3
"""Functional test of the web UI shares registry and attach flow.

Drives web/app.py's handlers directly (no HTTP server) against the real
create.sh engine in a temp PODS_DIR. No containers or podman needed:
installing only generates scripts. The share host paths point at /data
and /archive, which are deliberately NOT creatable in test environments -
that also exercises the warn-and-continue path for unmounted share roots.
"""
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pods = os.path.join(tempfile.mkdtemp(), "Pods")
os.makedirs(pods)
os.environ["APP_DIR"] = REPO
os.environ["PODS_DIR"] = pods
sys.path.insert(0, os.path.join(REPO, "web"))
import app  # noqa: E402


def check(cond, label):
    if not cond:
        print(f"FAIL: {label}")
        sys.exit(1)
    print(f"  ok: {label}")


# --- add two shares (one rw, one ro) ---
out = app.do_shares({"do": ["add"], "name": ["media"], "host_path": ["/data/"],
                     "container_path": [""]})
check(b"Added share" in out, "add rw share 'media'")
out = app.do_shares({"do": ["add"], "name": ["archive"], "host_path": ["/archive"],
                     "container_path": ["/archive"], "ro": ["on"]})
check(b"Added share" in out, "add ro share 'archive'")

shares = app.load_shares()
check(shares["media"] == {"host_path": "/data", "container_path": "/data",
                          "ro": False},
      "trailing slash stripped, cpath defaults to host path")
check(shares["archive"]["ro"] is True, "ro flag persisted")

# --- validation rejects bad input ---
check(b"Invalid name" in app.do_shares({"do": ["add"], "name": ["Bad_Name"],
                                        "host_path": ["/x"]}), "bad name rejected")
check(b"already exists" in app.do_shares({"do": ["add"], "name": ["media"],
                                          "host_path": ["/x"]}),
      "duplicate rejected")
check(b"absolute" in app.do_shares({"do": ["add"], "name": ["rel"],
                                    "host_path": ["data"]}),
      "relative path rejected")

# --- shares page renders ---
out = app.shares_page()
check(b"media" in out and b"archive" in out and b"read-only" in out,
      "shares page lists both")

# --- install a custom pod WITH the media share attached ---
form = {
    "custom": ["1"], "service": ["testpod"], "image": ["docker.io/alpine:latest"],
    "command": ["sleep infinity"], "ports": ["8080:8080"], "envlines": [""],
    "vollines": [f"/config={pods}/testpod/config"], "share.media": ["on"],
}
out = app.do_install(form)
check(b"installed" in out, "custom pod install with share succeeds")
info = app.pod_config("testpod")
check(info["volumes"] == {"/config": f"{pods}/testpod/config", "/data": "/data"},
      ".config.json volumes include the share mount")
check(info["shares"] == ["media"], ".config.json records the share by name")
run_sh = open(os.path.join(pods, "testpod", "run.sh")).read()
check("-v /data:/data \\" in run_sh, "run.sh mounts the rw share")

# --- attach the ro share to the existing pod ---
out = app.do_attach({"pod": ["testpod"], "share": ["archive"]}, app.load_shares())
check(b"ok" in out and b"Restart" in out, "attach to deployed pod succeeds")
info = app.pod_config("testpod")
check(info["shares"] == ["archive", "media"], "shares list updated")
check(info["volumes"]["/archive"] == "/archive:ro", "volume recorded with :ro")
run_sh = open(os.path.join(pods, "testpod", "run.sh")).read()
check("-v /archive:/archive:ro \\" in run_sh,
      "regenerated run.sh mounts read-only")
check("-v /data:/data \\" in run_sh, "existing share mount preserved")

# --- guards ---
out = app.do_attach({"pod": ["testpod"], "share": ["archive"]}, app.load_shares())
check(b"already attached" in out, "double-attach refused")
out = app.do_attach({"pod": ["nope"], "share": ["media"]}, app.load_shares())
check(b"Unknown pod or share" in out, "unknown pod refused")

# --- usage shows on the shares page; delete works ---
out = app.shares_page()
check(b"testpod" in out, "shares page shows pod usage")
out = app.do_shares({"do": ["delete"], "name": ["archive"]})
check(b"Deleted share" in out and "archive" not in app.load_shares(),
      "delete works")

print("WEB SHARES TEST PASSED")
