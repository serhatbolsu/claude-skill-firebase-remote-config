#!/usr/bin/env bash
# Fetch Remote Config versions + templates (with metadata injected) + experiments.
# Uses Firebase CLI when available (preferred — no token wrangling). Falls back
# to raw REST API with a bearer token if FIREBASE_CLI=0 or `firebase` is missing.
#
# Usage:
#   rc-fetch.sh <project_id> versions [--limit N | --range START END]
#   rc-fetch.sh <project_id> template <version_number>
#   rc-fetch.sh <project_id> experiments [--range START END]
#   rc-fetch.sh <project_id> resolve-version-at <rfc3339_timestamp>
#
# All output files land in /tmp/ and are reused on subsequent runs:
#   /tmp/rc-versions-<project_id>.json
#   /tmp/rc-v<N>.json                      (template + injected `version` block)
#   /tmp/rc-experiments-<project_id>.json
#
# Environment:
#   FIREBASE_CLI=0     force REST path
#   TOKEN              bearer token (REST path only; auto-resolved via gcloud if unset)
#   PROJECT_NUMBER     required for REST experiments path (auto-resolved if gcloud present)

set -euo pipefail

PROJECT_ID="${1:?project_id required}"
OP="${2:?op required: versions|template|experiments|resolve-version-at}"
shift 2

use_cli() {
  [ "${FIREBASE_CLI:-1}" = "1" ] && command -v firebase >/dev/null 2>&1
}

resolve_token() {
  if [ -n "${TOKEN:-}" ]; then echo "$TOKEN"; return; fi
  if command -v gcloud >/dev/null 2>&1; then
    gcloud auth application-default print-access-token 2>/dev/null && return
  fi
  echo "ERROR: no TOKEN env var set and gcloud not available" >&2
  exit 1
}

resolve_project_number() {
  if [ -n "${PROJECT_NUMBER:-}" ]; then echo "$PROJECT_NUMBER"; return; fi
  if command -v gcloud >/dev/null 2>&1; then
    gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)' 2>/dev/null && return
  fi
  local tok; tok=$(resolve_token)
  curl -sS -H "Authorization: Bearer $tok" \
    "https://firebase.googleapis.com/v1beta1/projects/${PROJECT_ID}" \
    | jq -r .projectNumber
}

# ---------- versions list ----------
op_versions() {
  local limit="" start="" end=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --limit) limit="$2"; shift 2;;
      --range) start="$2"; end="$3"; shift 3;;
      *) echo "unknown arg: $1" >&2; exit 2;;
    esac
  done
  local out="/tmp/rc-versions-${PROJECT_ID}.json"

  if use_cli; then
    local args=(--project="$PROJECT_ID" --json)
    [ -n "$limit" ] && args+=(--limit="$limit")
    [ -n "$start" ] && args+=(--start-time="$start")
    [ -n "$end" ]   && args+=(--end-time="$end")
    firebase remoteconfig:versions:list "${args[@]}" 2>/dev/null \
      | jq '.result' > "$out"
  else
    local tok; tok=$(resolve_token)
    local page_token=""; local acc='{"versions":[]}'
    while :; do
      local resp
      resp=$(curl -sS -G \
        "https://firebaseremoteconfig.googleapis.com/v1/projects/${PROJECT_ID}/remoteConfig:listVersions" \
        ${limit:+--data-urlencode "pageSize=${limit}"} \
        ${start:+--data-urlencode "startTime=${start}"} \
        ${end:+--data-urlencode "endTime=${end}"} \
        ${page_token:+--data-urlencode "pageToken=${page_token}"} \
        -H "Authorization: Bearer ${tok}")
      acc=$(jq -n --argjson a "$acc" --argjson b "$resp" \
        '{versions: ($a.versions + ($b.versions // []))}')
      page_token=$(echo "$resp" | jq -r '.nextPageToken // empty')
      [ -z "$page_token" ] || [ -n "$limit" ] && break
    done
    echo "$acc" > "$out"
  fi
  echo "$out"
}

# ---------- fetch one template + inject metadata ----------
op_template() {
  local V="${1:?version_number required}"
  local out="/tmp/rc-v${V}.json"
  # Reuse cached file
  if [ -f "$out" ] && jq -e '.version.versionNumber' "$out" >/dev/null 2>&1; then
    echo "$out"; return
  fi

  if use_cli; then
    firebase remoteconfig:get --project="$PROJECT_ID" --version-number="$V" --output="$out" >/dev/null 2>&1
  else
    local tok; tok=$(resolve_token)
    curl -sS \
      "https://firebaseremoteconfig.googleapis.com/v1/projects/${PROJECT_ID}/remoteConfig?versionNumber=${V}" \
      -H "Authorization: Bearer ${tok}" -o "$out"
  fi

  # Ensure versions metadata exists (fetch a wide window if not)
  local meta="/tmp/rc-versions-${PROJECT_ID}.json"
  [ -f "$meta" ] || op_versions --limit 300 >/dev/null

  # Inject `version` block matching this versionNumber
  jq --slurpfile m "$meta" --arg v "$V" \
    '. + {version: (($m[0].versions // [])[] | select(.versionNumber == $v))}' \
    "$out" > "${out}.tmp" && mv "${out}.tmp" "$out"
  echo "$out"
}

# ---------- experiments (with optional window filter) ----------
op_experiments() {
  local start="" end=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --range) start="$2"; end="$3"; shift 3;;
      *) echo "unknown arg: $1" >&2; exit 2;;
    esac
  done
  local out="/tmp/rc-experiments-${PROJECT_ID}.json"
  local raw="/tmp/rc-experiments-raw-${PROJECT_ID}.json"

  if use_cli; then
    firebase remoteconfig:experiments:list --project="$PROJECT_ID" --json 2>/dev/null \
      | jq '.result' > "$raw"
  else
    local tok; tok=$(resolve_token)
    local pn; pn=$(resolve_project_number)
    local page_token=""; local acc='{"experiments":[]}'
    while :; do
      local resp
      resp=$(curl -sS -G \
        "https://firebaseremoteconfig.googleapis.com/v1/projects/${pn}/namespaces/firebase:listExperiments" \
        --data-urlencode "pageSize=100" \
        ${page_token:+--data-urlencode "pageToken=${page_token}"} \
        -H "Authorization: Bearer ${tok}")
      acc=$(jq -n --argjson a "$acc" --argjson b "$resp" \
        '{experiments: ($a.experiments + ($b.experiments // []))}')
      page_token=$(echo "$resp" | jq -r '.nextPageToken // empty')
      [ -z "$page_token" ] && break
    done
    echo "$acc" > "$raw"
  fi

  # Filter overlap with [start, end] if provided
  jq --arg ws "${start:-0001-01-01T00:00:00Z}" --arg we "${end:-9999-12-31T00:00:00Z}" '
    def overlaps:
      (.startTime // "9999-12-31T00:00:00Z") as $s
      | (if (.state // "") == "RUNNING" then "9999-12-31T00:00:00Z"
         else (.endTime // .lastUpdateTime // .startTime // "0001-01-01T00:00:00Z") end) as $e
      | ($s <= $we) and ($e >= $ws);
    {window_start: $ws, window_end: $we, experiments: [(.experiments // .[] // [])[]? | select(overlaps)]}
  ' "$raw" > "$out"
  echo "$out"
}

# ---------- resolve "state at date D" ----------
op_resolve_version_at() {
  local at="${1:?rfc3339 timestamp required}"
  local meta="/tmp/rc-versions-${PROJECT_ID}.json"

  if use_cli; then
    firebase remoteconfig:versions:list --project="$PROJECT_ID" \
      --end-time="$at" --limit=1 --json 2>/dev/null \
      | jq -r '.result.versions[0].versionNumber // empty'
  else
    local tok; tok=$(resolve_token)
    curl -sS -G \
      "https://firebaseremoteconfig.googleapis.com/v1/projects/${PROJECT_ID}/remoteConfig:listVersions" \
      --data-urlencode "endTime=$at" --data-urlencode "pageSize=1" \
      -H "Authorization: Bearer ${tok}" \
      | jq -r '.versions[0].versionNumber // empty'
  fi
}

case "$OP" in
  versions)            op_versions "$@";;
  template)            op_template "$@";;
  experiments)         op_experiments "$@";;
  resolve-version-at)  op_resolve_version_at "$@";;
  *) echo "unknown op: $OP" >&2; exit 2;;
esac
