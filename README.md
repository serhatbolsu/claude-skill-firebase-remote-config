# serhat-skills — Claude Code marketplace

A small marketplace of Claude Code plugins. Add this marketplace once, then install individual plugins.

## Quick install

```
/plugin marketplace add serhatbolsu/firebase-rc-skill-plugin
/plugin install firebase-remote-config@serhat-skills
```

Replace `serhatbolsu/firebase-rc-skill-plugin` with the actual GitHub path once published.

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

**Auth (auto-detected in this order):**
1. Firebase CLI (`firebase login`) — recommended
2. `gcloud auth application-default print-access-token`
3. Service account JSON via `GOOGLE_APPLICATION_CREDENTIALS`

The principal needs Remote Config + A/B Testing read access (e.g., `Firebase Viewer` role).

**Requirements:** `python3`, `jq`, `curl`. `firebase` CLI strongly recommended.

After installing, ask Claude something like:
- "What changed in Remote Config between 2026-04-01 and 2026-05-01 in project X?"
- "Show me the last 5 Remote Config changes in project X"
- "Which A/B tests were running last month in project X?"
- "Diff version 42 vs 47 in project X"

## License

MIT
