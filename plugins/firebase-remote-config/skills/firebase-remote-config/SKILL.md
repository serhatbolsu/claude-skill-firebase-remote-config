---
name: firebase-remote-config
description: Diff Firebase Remote Config parameters and conditions between two dates (or version numbers), list every config change in a window, AND correlate those changes with the Firebase A/B tests running over the same window — so the user can see which parameter/condition changes overlap with active experiments. Outputs structured JSON suitable for downstream impact analysis. Use when the user asks what changed in Remote Config, who changed it, between which dates, which experiments were active, or wants to feed RC changes + experiment state into impact/effect measurement.
---

# Firebase Remote Config — Diff, Changelog & A/B Test Overlay

Read-only skill that answers:

1. **Diff between two dates** — what differs in parameters & conditions between the templates live at date A vs. date B.
2. **Diff between two version numbers** — same, by version.
3. **Full changelog across a date range** — every version transition with param/condition diff + author + timestamp.
4. **A/B tests in a window** — which Firebase A/B tests were active over `[A, B]`, the RC parameters/conditions each touches, state, variants.

For (1) and (3) the skill **cross-references** the diff with experiments — when a param/condition appears in both, it's flagged with ⚠ in the human render and an `overlapping_experiments` array in the JSON.

## Scripts (already installed, do not rewrite)

All helper scripts live in `~/.claude/skills/firebase-remote-config/scripts/`. They are **persistent and idempotent** — do not re-create them in `/tmp/` each session.

Refer to this dir as `$SKILL_DIR` below:
```bash
SKILL_DIR="$HOME/.claude/skills/firebase-remote-config/scripts"
```

Files in `$SKILL_DIR/`:
- `rc-fetch.sh` — fetch versions list, fetch one template (with metadata injected), fetch experiments (with window filter), resolve "version live at date D". Auto-detects Firebase CLI vs. raw REST.
- `rc-diff.py` — diff two template JSON files
- `rc-overlay.py` — annotate a diff with overlapping experiments
- `rc-changelog.py` — build per-transition changelog with overlay
- `rc-render.py` — human-readable summary (drills into `defaultValue`, `conditionalValues[<cond>]`, `description`, `valueType` per changed parameter)

Output files all land in `/tmp/`:
- `/tmp/rc-versions-<project_id>.json`
- `/tmp/rc-v<N>.json` (template + injected `version` metadata block)
- `/tmp/rc-experiments-<project_id>.json`
- `/tmp/rc-diff-<A>-<B>.json` (optional, when caller saves it)
- `/tmp/rc-changelog-<...>.json`

`rc-fetch.sh` caches template files — re-running with the same version number is a no-op once cached. Delete the cached file to force re-fetch.

## Prerequisites — resolve in this order

1. **Project ID** — ask user, or read `projects.default` from `.firebaserc` in cwd, or grep `PROJECT_ID` from a `GoogleService-Info.plist` / `google-services.json` in the repo.

2. **Auth** — `rc-fetch.sh` auto-selects:
   - **Preferred (Option 0): Firebase CLI** — if `firebase` is on PATH and `firebase login:list` shows an authed user, the script uses it directly. No token handling, no project-number resolution. If logged out, prompt user to run `! firebase login` (browser popup).
   - **Fallback: bearer token** — set `TOKEN=$(gcloud auth application-default print-access-token)` or use the service-account JWT minter in [Auth resolution — REST fallback](#auth-resolution--rest-fallback). Set `FIREBASE_CLI=0` to force this path.
   - The principal needs read access to Remote Config and A/B Testing (`Firebase Viewer` is the simplest role).

3. **Project number** — only required for the REST experiments path. `rc-fetch.sh` resolves it from `gcloud projects describe` or the Firebase Management API. Skip when using the Firebase CLI path.

4. **Tools** — `curl`, `jq`, `python3` (always). `firebase` CLI strongly preferred.

If a prerequisite is missing, stop and tell the user the one specific thing that's blocked rather than dumping the full list.

## Core concept: "state at date D"

Firebase RC versions are point-in-time snapshots. The template live at instant D is the version with the largest `updateTime` ≤ D. To diff between dates A and B:

1. `versionA` = state at A   (`rc-fetch.sh ... resolve-version-at A`)
2. `versionB` = state at B   (`rc-fetch.sh ... resolve-version-at B`)
3. Fetch each template via `rc-fetch.sh ... template <N>` — this injects the metadata block.
4. Diff + overlay + render.

If A predates the API's ~300-day retention, `resolve-version-at` returns empty. Say so explicitly; ask whether to use the earliest available.

## Operations

In all examples below: `PROJ=<project_id>`, `SKILL_DIR=$HOME/.claude/skills/firebase-remote-config/scripts`.

### Op 1 — Diff between two dates (with experiment overlay)

```bash
DATE_A="2026-04-01T00:00:00Z"
DATE_B="2026-05-01T00:00:00Z"

VA=$("$SKILL_DIR/rc-fetch.sh" "$PROJ" resolve-version-at "$DATE_A")
VB=$("$SKILL_DIR/rc-fetch.sh" "$PROJ" resolve-version-at "$DATE_B")
echo "Versions: $VA → $VB"

"$SKILL_DIR/rc-fetch.sh" "$PROJ" template "$VA" >/dev/null
"$SKILL_DIR/rc-fetch.sh" "$PROJ" template "$VB" >/dev/null

EXP=$("$SKILL_DIR/rc-fetch.sh" "$PROJ" experiments --range "$DATE_A" "$DATE_B")

python3 "$SKILL_DIR/rc-diff.py" "/tmp/rc-v${VA}.json" "/tmp/rc-v${VB}.json" \
  | python3 "$SKILL_DIR/rc-overlay.py" "$EXP" \
  > "/tmp/rc-diff-${VA}-${VB}.json"

python3 "$SKILL_DIR/rc-render.py" diff "/tmp/rc-diff-${VA}-${VB}.json"
```

Edge cases:
- `VA` empty → no version existed at/before A within retention. Ask user.
- `VA == VB` → no template changes between dates. Still run experiments fetch — experiments may have started/stopped without a template change.

### Op 2 — Diff between two version numbers

```bash
VA=42; VB=47
"$SKILL_DIR/rc-fetch.sh" "$PROJ" template "$VA" >/dev/null
"$SKILL_DIR/rc-fetch.sh" "$PROJ" template "$VB" >/dev/null

# Derive window from the two versions' updateTime
DATE_A=$(jq -r '.version.updateTime' "/tmp/rc-v${VA}.json")
DATE_B=$(jq -r '.version.updateTime' "/tmp/rc-v${VB}.json")
EXP=$("$SKILL_DIR/rc-fetch.sh" "$PROJ" experiments --range "$DATE_A" "$DATE_B")

python3 "$SKILL_DIR/rc-diff.py" "/tmp/rc-v${VA}.json" "/tmp/rc-v${VB}.json" \
  | python3 "$SKILL_DIR/rc-overlay.py" "$EXP" \
  > "/tmp/rc-diff-${VA}-${VB}.json"

python3 "$SKILL_DIR/rc-render.py" diff "/tmp/rc-diff-${VA}-${VB}.json"
```

### Op 3 — Full changelog over a date range

```bash
START="2026-04-01T00:00:00Z"
END="2026-05-01T00:00:00Z"

"$SKILL_DIR/rc-fetch.sh" "$PROJ" versions --range "$START" "$END" >/dev/null

# Baseline = version live just before START (so first transition is a real diff)
BASELINE=$("$SKILL_DIR/rc-fetch.sh" "$PROJ" resolve-version-at "$START")

# Build oldest-first version list: [BASELINE, v_oldest_in_range, ..., v_newest_in_range]
VERSIONS=$( ( [ -n "$BASELINE" ] && echo "$BASELINE"; \
              jq -r '.versions[].versionNumber' "/tmp/rc-versions-${PROJ}.json" | tac ) | uniq )

for V in $VERSIONS; do
  "$SKILL_DIR/rc-fetch.sh" "$PROJ" template "$V" >/dev/null
done

EXP=$("$SKILL_DIR/rc-fetch.sh" "$PROJ" experiments --range "$START" "$END")

python3 "$SKILL_DIR/rc-changelog.py" "$SKILL_DIR" "$PROJ" "$EXP" $VERSIONS \
  > "/tmp/rc-changelog-${START%T*}-to-${END%T*}.json"

python3 "$SKILL_DIR/rc-render.py" changelog "/tmp/rc-changelog-${START%T*}-to-${END%T*}.json"
```

### Op 3-lite — "Last N changes" (no date range)

```bash
N=5

"$SKILL_DIR/rc-fetch.sh" "$PROJ" versions --limit $((N+1)) >/dev/null

# Versions are newest-first in the list — reverse for oldest-first
VERSIONS=$(jq -r '.versions[].versionNumber' "/tmp/rc-versions-${PROJ}.json" | tac)

for V in $VERSIONS; do
  "$SKILL_DIR/rc-fetch.sh" "$PROJ" template "$V" >/dev/null
done

# Window for experiments = oldest to newest of the N+1 versions
DATE_A=$(jq -r '.versions[-1].updateTime' "/tmp/rc-versions-${PROJ}.json")
DATE_B=$(jq -r '.versions[0].updateTime'  "/tmp/rc-versions-${PROJ}.json")
EXP=$("$SKILL_DIR/rc-fetch.sh" "$PROJ" experiments --range "$DATE_A" "$DATE_B")

python3 "$SKILL_DIR/rc-changelog.py" "$SKILL_DIR" "$PROJ" "$EXP" $VERSIONS \
  > "/tmp/rc-changelog-last${N}.json"

python3 "$SKILL_DIR/rc-render.py" changelog "/tmp/rc-changelog-last${N}.json"
```

### Op 4 — List A/B tests in a window (standalone)

```bash
EXP=$("$SKILL_DIR/rc-fetch.sh" "$PROJ" experiments --range "$DATE_A" "$DATE_B")
jq '.experiments[] | {
  name: .name,
  displayName: (.definition.displayName // .displayName),
  state, startTime,
  endTime: (.endTime // .lastUpdateTime),
  params: [.definition.experimentParameters.parameters? // {} | keys[]],
  conditions: [.definition.experimentConditions?[]?.name]
}' "$EXP"
```

## Auth resolution — REST fallback

Only needed when `FIREBASE_CLI=0` or `firebase` isn't installed.

1. **`GOOGLE_APPLICATION_CREDENTIALS`** points to a service account JSON. Mint a token (requires `pip install cryptography` once). Use scope `https://www.googleapis.com/auth/firebase` — works for both Remote Config and A/B Testing.

   ```bash
   export TOKEN=$(python3 <<'PY'
   import json, time, base64, urllib.request, urllib.parse, os
   from cryptography.hazmat.primitives import hashes, serialization
   from cryptography.hazmat.primitives.asymmetric import padding
   c = json.load(open(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]))
   now = int(time.time())
   header = {"alg":"RS256","typ":"JWT","kid":c["private_key_id"]}
   claim = {"iss":c["client_email"],
            "scope":"https://www.googleapis.com/auth/firebase",
            "aud":"https://oauth2.googleapis.com/token","iat":now,"exp":now+3600}
   b64=lambda d: base64.urlsafe_b64encode(json.dumps(d,separators=(",",":")).encode()).rstrip(b"=")
   si = b64(header)+b"."+b64(claim)
   key = serialization.load_pem_private_key(c["private_key"].encode(), password=None)
   sig = key.sign(si, padding.PKCS1v15(), hashes.SHA256())
   jwt = (si+b"."+base64.urlsafe_b64encode(sig).rstrip(b"=")).decode()
   data = urllib.parse.urlencode({"grant_type":"urn:ietf:params:oauth:grant-type:jwt-bearer","assertion":jwt}).encode()
   print(json.loads(urllib.request.urlopen("https://oauth2.googleapis.com/token", data=data).read())["access_token"])
   PY
   )
   ```

2. **`gcloud`** is installed and authed:
   ```bash
   export TOKEN=$(gcloud auth application-default print-access-token)
   ```

3. Else prompt the user for an SA JSON path or to run `firebase login` / `gcloud auth application-default login`. Do not proceed without auth.

## Output style for the user

After running, summarize from the rendered output. The render script already drills into changes correctly — surface its output, then add headline stats:

```
Project: <id>   Window: <date_a> → <date_b>   (versions <VA> → <VB>, N transitions)

Parameters:  +<a>  -<r>  ~<c>
Conditions:  +<a>  -<r>  ~<c>

Experiments in window: <N>  (RUNNING: <k>, DONE: <j>)
  - <displayName>  [<state>]  <start> → <end>
       params:     <p1>, <p2>
       conditions: <c1>

⚠ Overlaps:
  <list of param/condition keys that changed AND had an experiment touching them>

(then the rendered per-transition output from rc-render.py)
```

If no overlaps, say "No experiments overlapped the changed parameters/conditions in this window."

## For downstream impact analysis

`/tmp/rc-diff-*.json` and `/tmp/rc-changelog-*.json` are the canonical inputs. Each entry carries:

- Changed param key + full `from`/`to` (with `defaultValue` and `conditionalValues` per condition)
- `to_update_time` per change — breakpoint timestamp for before/after metrics
- `to_user`, `to_origin` (CONSOLE / REST_API / ADMIN_SDK_NODE / etc.) — distinguish human edits from automation
- Condition diffs — often the actual cause of population-level metric shifts
- `overlapping_experiments` per change — for triaging confounded vs. clean attribution
- `experiment_overlap_summary` — flat (target, type, experiments[]) list, easy to join
- `experiment_window` — boundary timestamps

When the user follows up with "now measure the impact," **do not re-fetch** — read the existing JSON from `/tmp/`. If older than 24h or missing, re-run.

## Triage heuristics for the impact layer

- **Confounded change**: param has a manual edit AND `overlapping_experiments` is non-empty → exclude from causal claims, or analyze inside vs. outside the experiment's exposure window.
- **Pure manual change**: `overlapping_experiments: []` → safe to attribute to the edit.
- **Pure experiment change**: template diff is `is_empty: true` for the window but experiments are RUNNING → metric shift is the experiment, not config drift.
- **Flip-flop pattern**: same param toggled back-and-forth multiple times in a short window (e.g., `true→false→true→false`) → likely manual testing, not a real change. Treat the whole sequence as one event ending at the final value, or exclude from impact analysis.

## Gotchas

- `listVersions` retention is ~300 days. Date ranges older than that return empty.
- `listVersions` does **not** include parameter bodies — `rc-fetch.sh template <N>` does that per version.
- The Firebase CLI path needs you logged in (`firebase login`). It uses your Google account's permissions — make sure that account has Remote Config + A/B Testing read on the target project.
- A/B Testing REST endpoint requires project **number** (numeric), not project ID. The fallback path resolves it automatically via gcloud or the Firebase Management API. The CLI path doesn't care.
- Newly-created RC conditions can be side-effects of an experiment launch, not manual edits — the `overlapping_experiments` annotation surfaces this.
- The A/B Testing API's `definition.experimentParameters.parameters` and `definition.experimentConditions` shape varies across experiment service types (Remote Config vs. Notifications). The overlay treats missing fields as "no params/conditions touched" rather than erroring.
- Bare dates like `2026-04-01` must be normalized to RFC3339 (`2026-04-01T00:00:00Z`). Tell the user when you auto-normalize.
- Byte-identical rollback versions: changelog marks them `is_empty: true`; render skips them.
- `rc-fetch.sh template` caches templates — to force re-fetch (e.g., if the cached file is missing the `version` metadata for some reason), `rm /tmp/rc-v<N>.json` first.
