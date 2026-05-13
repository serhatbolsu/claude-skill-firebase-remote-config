#!/usr/bin/env python3
"""Diff two Firebase Remote Config template JSON files.

Each input file should be a template with a `version` block injected from
listVersions (rc-fetch.sh does this). If `version` is missing, meta fields
come back null.

Output (stdout): JSON with keys parameters, conditions, parameter_groups, meta.
"""
import json, sys, os

def load(p):
    with open(p) as f: return json.load(f)

def diff_params(pa, pb):
    added = {k: pb[k] for k in sorted(set(pb) - set(pa))}
    removed = sorted(set(pa) - set(pb))
    changed = [{"key": k, "from": pa[k], "to": pb[k]}
               for k in sorted(set(pa) & set(pb)) if pa[k] != pb[k]]
    return {"added": added, "removed": removed, "changed": changed}

def diff_conditions(ca, cb):
    ma = {c["name"]: c for c in ca or []}
    mb = {c["name"]: c for c in cb or []}
    added = [mb[n] for n in sorted(set(mb) - set(ma))]
    removed = [ma[n] for n in sorted(set(ma) - set(mb))]
    changed = [{"name": n, "from": ma[n], "to": mb[n]}
               for n in sorted(set(ma) & set(mb)) if ma[n] != mb[n]]
    return {"added": added, "removed": removed, "changed": changed}

def diff_param_groups(ga, gb):
    ga, gb = ga or {}, gb or {}
    added = [{"group": g, "value": gb[g]} for g in sorted(set(gb) - set(ga))]
    removed = sorted(set(ga) - set(gb))
    changed = []
    for g in sorted(set(ga) & set(gb)):
        if ga[g] != gb[g]:
            inner = diff_params(ga[g].get("parameters") or {}, gb[g].get("parameters") or {})
            changed.append({"group": g, "parameters": inner})
    return {"added": added, "removed": removed, "changed": changed}

def main():
    a = load(sys.argv[1]); b = load(sys.argv[2])
    va = a.get("version") or {}
    vb = b.get("version") or {}
    out = {
        "parameters": diff_params(a.get("parameters") or {}, b.get("parameters") or {}),
        "conditions": diff_conditions(a.get("conditions"), b.get("conditions")),
        "parameter_groups": diff_param_groups(a.get("parameterGroups"), b.get("parameterGroups")),
        "meta": {
            "from_file": os.path.basename(sys.argv[1]),
            "to_file": os.path.basename(sys.argv[2]),
            "from_version": va.get("versionNumber"),
            "to_version":   vb.get("versionNumber"),
            "from_update_time": va.get("updateTime"),
            "to_update_time":   vb.get("updateTime"),
            "from_user": (va.get("updateUser") or {}).get("email"),
            "to_user":   (vb.get("updateUser") or {}).get("email"),
            "from_origin": va.get("updateOrigin"),
            "to_origin":   vb.get("updateOrigin"),
            "to_description": vb.get("description"),
        },
    }
    json.dump(out, sys.stdout, indent=2, default=str)

if __name__ == "__main__": main()
