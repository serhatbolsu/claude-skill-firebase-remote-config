#!/usr/bin/env python3
"""Build a per-version changelog with experiment overlay.
Args: <scripts_dir> <project_id> <experiments_json_path> <v1> <v2> ... <vN> (oldest-first)
"""
import json, sys, subprocess, os

scripts_dir = sys.argv[1]
project_id = sys.argv[2]
exp_path = sys.argv[3]
versions = sys.argv[4:]

entries = []
for i in range(1, len(versions)):
    a, b = versions[i-1], versions[i]
    diff_proc = subprocess.run(
        ["python3", os.path.join(scripts_dir, "rc-diff.py"),
         f"/tmp/rc-v{a}.json", f"/tmp/rc-v{b}.json"],
        capture_output=True, text=True, check=True,
    )
    overlay_proc = subprocess.run(
        ["python3", os.path.join(scripts_dir, "rc-overlay.py"), exp_path],
        input=diff_proc.stdout, capture_output=True, text=True, check=True,
    )
    d = json.loads(overlay_proc.stdout)
    p, c, g = d["parameters"], d["conditions"], d["parameter_groups"]
    is_empty = not (p["added"] or p["removed"] or p["changed"]
                    or c["added"] or c["removed"] or c["changed"]
                    or g["added"] or g["removed"] or g["changed"])
    entries.append({
        "project_id": project_id,
        "from_version": a,
        "to_version": b,
        "to_update_time": d["meta"]["to_update_time"],
        "to_user": d["meta"]["to_user"],
        "to_origin": d["meta"].get("to_origin"),
        "is_empty": is_empty,
        "diff": d,
    })

json.dump(entries, sys.stdout, indent=2, default=str)
