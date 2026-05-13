#!/usr/bin/env python3
"""Read a diff JSON from stdin and an experiments JSON file from argv[1].
Annotate each changed/added/removed parameter and condition with the list of
overlapping experiments. Emit annotated diff JSON to stdout.

Experiments JSON is the output of rc-fetch.sh's experiments step:
  {window_start, window_end, experiments: [...]}
"""
import json, sys

diff = json.load(sys.stdin)
with open(sys.argv[1]) as f:
    exp_payload = json.load(f)
experiments = exp_payload.get("experiments", [])

def exp_params(e):
    d = (e.get("definition") or {})
    ep = (d.get("experimentParameters") or {}).get("parameters") or {}
    return list(ep.keys())

def exp_conditions(e):
    d = (e.get("definition") or {})
    return [c.get("name") for c in (d.get("experimentConditions") or []) if c.get("name")]

param_idx, cond_idx = {}, {}
for e in experiments:
    summary = {
        "name": e.get("name"),
        "displayName": (e.get("definition") or {}).get("displayName") or e.get("displayName"),
        "state": e.get("state"),
        "startTime": e.get("startTime"),
        "endTime": e.get("endTime") or (e.get("lastUpdateTime") if e.get("state") != "RUNNING" else None),
    }
    for p in exp_params(e):
        param_idx.setdefault(p, []).append(summary)
    for c in exp_conditions(e):
        cond_idx.setdefault(c, []).append(summary)

def tag_param(key): return param_idx.get(key, [])
def tag_cond(name): return cond_idx.get(name, [])

p = diff["parameters"]
p["added"]   = {k: {"value": v, "overlapping_experiments": tag_param(k)} for k, v in p["added"].items()}
p["removed"] = [{"key": k, "overlapping_experiments": tag_param(k)} for k in p["removed"]]
for c in p["changed"]:
    c["overlapping_experiments"] = tag_param(c["key"])

c = diff["conditions"]
c["added"]   = [{**x, "overlapping_experiments": tag_cond(x.get("name"))} for x in c["added"]]
c["removed"] = [{**x, "overlapping_experiments": tag_cond(x.get("name"))} for x in c["removed"]]
for x in c["changed"]:
    x["overlapping_experiments"] = tag_cond(x.get("name"))

summary = []
for k, exps in param_idx.items():
    summary.append({"target": k, "type": "parameter", "experiments": exps})
for n, exps in cond_idx.items():
    summary.append({"target": n, "type": "condition", "experiments": exps})

diff["experiments"] = experiments
diff["experiment_overlap_summary"] = summary
diff["experiment_window"] = {
    "start": exp_payload.get("window_start"),
    "end": exp_payload.get("window_end"),
}

json.dump(diff, sys.stdout, indent=2, default=str)
