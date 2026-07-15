# Changelog

## v0.6.0 — onboarding: credential wizard + auto-minted keys (2026-07-15)

The release that removes both manual steps from a fresh install: no more
hand-crafting `.tsapi.json`, no more pasting auth keys per service.

### Features

- **First-run API-credential wizard** (Settings page, and embedded wherever
  an API-requiring action first hits a missing credential — the Users page
  and both install forms). Explains the required Tailscale OAuth scopes
  (Devices/Core, Auth Keys, Policy File — all write) and the
  `tag:tailarr-ctrl` tagging, deep-links to the admin console, and handles
  the tag-not-selectable-yet case (paste-in `tagOwners` snippet, or
  bootstrap via a static API access token). Accepts an OAuth client id +
  secret or a static `{"token": "tskey-api-…"}`; validates live with
  read-only calls and reports per-capability pass/fail before saving
  `Pods/.tsapi.json` with 0600 perms. Can also initialize the three
  `tailarr-managed` policy fences (the adopt path) so policy sync never
  fails closed with "managed sections missing" on a fresh tailnet.
  New endpoints: `GET /api/tsapi`, `POST /api/tsapi/validate`,
  `POST /api/tsapi`, `POST /api/tsapi/fences`.
- **Auto-minted auth keys on deploy.** With a credential configured,
  installing a service mints its own single-use, preauthorized,
  non-ephemeral `tag:tailarr` key (7-day TTL) via the keys API and writes it
  to the pod's key file (0600) — zero manual key entry. Pasting a key still
  works as an override; without a credential the old paste-or-error flow is
  unchanged (and now points at the wizard). The install forms collapse the
  auth-key field into an "Advanced" override once a credential exists.
- Version surfaced: `VERSION` constant in the controller, shown in the
  sidebar footer and on `GET /api/info`.

### Fixes

- **Deploys can no longer die on log initialization** (seen in production
  after a controller restart: `touch: ./.deployment.log: No such file or
  directory` before any other output). `LOG_FILE`/`ERROR_LOG_FILE` now
  resolve to absolute paths (the service dir, with a tmp fallback), logging
  no longer initializes at source time, every log-file write is best-effort
  (WARN and continue — never abort a deploy over a log file), and the
  controller runs `create.sh` from the pod's own directory with pinned
  absolute log paths instead of depending on an ambient CWD.
- **Boot-recovery wipe is no longer destructive on a healthy stack.**
  `start-pods.sh` (installed by `bootstrap-tailarr.sh`) only wipes podman's
  runroot when the API socket is genuinely unreachable AND no containers
  are Up — running it by hand on a live fleet no longer drops every
  container to `Created`.

### Compatibility

- Existing installs keep working unchanged: a hand-written `.tsapi.json`
  is picked up as before, pasted auth keys still win over minting, and the
  policy-sync fail-closed and `tag:tailarr*` prefix invariants are intact.

## v0.5.1 and earlier

See the git tag history (`git log v0.4.0..v0.5.1 --oneline`) — releases
predate this changelog.
