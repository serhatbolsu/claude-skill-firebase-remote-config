# serhat-skills — Claude Code marketplace

A small marketplace of Claude Code plugins. Add this marketplace once, then install individual plugins.

## Prerequisites

Before installing, make sure you have:

- **Claude Code** — CLI, Desktop app, or an IDE extension (VS Code / JetBrains).
  Browser Claude Code (claude.ai/code) is **not supported** — the skill calls local CLIs that don't exist in the browser sandbox.
- **Firebase CLI** — `npm i -g firebase-tools`, then run `firebase login` (opens a browser).
  This is the simplest auth path. Alternatives below if you prefer not to install it.
- **Standard CLI tools** — `python3`, `jq`, `curl` (default on macOS, install via your package manager on Linux).
- **A Google account with Firebase access** — at least the `Firebase Viewer` role on the Firebase projects you want to query (read-only is sufficient — the skill never writes).

### Auth alternatives to the Firebase CLI

The skill auto-detects auth in this order:
1. **Firebase CLI** (recommended) — `firebase login`
2. **gcloud** — `gcloud auth application-default login`
3. **Service account JSON** — `export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json`
   (SA needs `Firebase Remote Config Viewer` + read access to A/B Testing, or just `Firebase Viewer`.)

## Quick install

Inside Claude Code (CLI/Desktop/IDE), run:

```
/plugin marketplace add serhatbolsu/claude-skill-firebase-remote-config
/plugin install firebase-remote-config@serhat-skills
```

Updates: just `/plugin update` whenever the repo gets new commits. No version bumps needed — every commit auto-counts as a release.

## Plugins

### `firebase-remote-config`

Diff Firebase Remote Config parameters and conditions between two dates (or version numbers), list every change in a window, and **correlate changes with Firebase A/B tests** that were running over the same window — so you can tell whether a metric shift came from a manual config edit, an experiment rollout, or both.

Read-only. Outputs structured JSON suitable for downstream impact analysis.

**Capabilities:**
- Diff between two dates → resolves which template version was live at each date, then diffs
- Diff between two version numbers
- Full changelog over a date range (every transition with who/when/origin)
- "Last N changes" workflow (no date range needed)
- A/B test overlay — every changed parameter/condition is annotated with the experiments that touched it during the window
- Drills into `defaultValue`, per-condition `conditionalValues`, `description`, `valueType` — surfaces what *actually* changed, not just "param changed"

See [Prerequisites](#prerequisites) above for auth and tooling requirements.

After installing, ask Claude something like:
- "What changed in Remote Config between 2026-04-01 and 2026-05-01 in project X?"
- "Show me the last 5 Remote Config changes in project X"
- "Which A/B tests were running last month in project X?"
- "Diff version 42 vs 47 in project X"

## License

MIT
