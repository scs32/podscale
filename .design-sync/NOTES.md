# design-sync notes

**Target project:** "Tailarr" on claude.ai/design — projectId
`a5989aac-f7a7-4e2d-b1a6-33d0d99d3d7e` (pinned in `config.json`).

**This design system does NOT use the converter.** It is intentionally a set
of hand-authored HTML `@dsCard` preview cards, not a compiled component
library:

- The design system lives in **`design/`**: `tailarr.css` (the token +
  component-class source of truth, Tailnet theme) and `components/*.html`
  (12 `@dsCard` previews) + `index.html` (kitchen-sink) + `README.md`.
- This repo has **no Storybook** and **no component-library package**. `web/ui`
  is a Vite *application* (React SPA), not a buildable/isolable component
  library, so the `/design-sync` converter (Storybook/package shapes) does not
  apply. `web/ui` implements the same design-system classes as the app.

**To refresh the sync** (after editing anything in `design/`): re-push the
`design/` sources directly with the `DesignSync` tool — `finalize_plan`
(writes `tailarr.css`, `index.html`, `README.md`, `components/*.html`;
deletes `[]`) then `write_files` from `localDir: design/`. Do NOT delete the
app-generated `_ds_bundle.js` / `_ds_manifest.json` / `_adherence.oxlintrc.json`
files in the project — Claude Design maintains those.
