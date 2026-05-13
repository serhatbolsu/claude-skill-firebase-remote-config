#!/usr/bin/env python3
"""Render a diff JSON (or changelog JSON) as a human-readable summary.

Crucially, drills into each changed parameter to surface what *actually* changed
(defaultValue, conditionalValues per condition, description, valueType) — not
just "param X changed".

Usage:
  python3 rc-render.py diff <diff.json>
  python3 rc-render.py changelog <changelog.json>
"""
import json, sys

def fmt_value(v):
    if v is None: return "∅"
    if isinstance(v, dict):
        if "value" in v: return repr(v["value"])
        if "useInAppDefault" in v: return "<in-app default>"
    return json.dumps(v, sort_keys=True)

def drill_param_change(c):
    """Yield human-readable bullets for what changed inside a parameter."""
    a, b = c["from"], c["to"]
    key = c["key"]
    exps = c.get("overlapping_experiments") or []
    exp_tag = f"  ⚠ experiment overlap: {', '.join(e['displayName'] or e['name'] for e in exps)}" if exps else ""

    # defaultValue
    if a.get("defaultValue") != b.get("defaultValue"):
        yield f"  ~ {key}.defaultValue: {fmt_value(a.get('defaultValue'))} → {fmt_value(b.get('defaultValue'))}{exp_tag}"

    # conditionalValues per-condition
    ac = a.get("conditionalValues") or {}
    bc = b.get("conditionalValues") or {}
    for cond in sorted(set(bc) - set(ac)):
        yield f"  + {key}.conditionalValues[{cond!r}] = {fmt_value(bc[cond])}{exp_tag}"
    for cond in sorted(set(ac) - set(bc)):
        yield f"  - {key}.conditionalValues[{cond!r}] (was {fmt_value(ac[cond])}){exp_tag}"
    for cond in sorted(set(ac) & set(bc)):
        if ac[cond] != bc[cond]:
            yield f"  ~ {key}.conditionalValues[{cond!r}]: {fmt_value(ac[cond])} → {fmt_value(bc[cond])}{exp_tag}"

    # description / valueType (lower-signal, surface only if changed)
    if a.get("description") != b.get("description"):
        yield f"  ~ {key}.description changed"
    if a.get("valueType") != b.get("valueType"):
        yield f"  ~ {key}.valueType: {a.get('valueType')} → {b.get('valueType')}"

    # If nothing surfaced (full-object replacement with no detectable inner diff)
    if a == b:
        return
    # Already covered above; fallthrough catch handled by yields

def drill_condition_change(c):
    a, b = c["from"], c["to"]
    name = c["name"]
    exps = c.get("overlapping_experiments") or []
    exp_tag = f"  ⚠ experiment overlap: {', '.join(e['displayName'] or e['name'] for e in exps)}" if exps else ""
    if a.get("expression") != b.get("expression"):
        yield f"  ~ condition {name!r}.expression:"
        yield f"      from: {a.get('expression')}"
        yield f"      to:   {b.get('expression')}{exp_tag}"
    if a.get("tagColor") != b.get("tagColor"):
        yield f"  ~ condition {name!r}.tagColor: {a.get('tagColor')} → {b.get('tagColor')}"

def render_diff(d, header=True):
    lines = []
    m = d["meta"]
    if header:
        lines.append(f"v{m.get('from_version')} → v{m.get('to_version')}  "
                     f"({m.get('to_update_time') or '?'}, {m.get('to_user') or '?'}, "
                     f"origin={m.get('to_origin') or '?'})")

    p, c, g = d["parameters"], d["conditions"], d["parameter_groups"]
    counts = (f"params: +{len(p['added'])} -{len(p['removed'])} ~{len(p['changed'])}  "
              f"conditions: +{len(c['added'])} -{len(c['removed'])} ~{len(c['changed'])}  "
              f"groups: +{len(g['added'])} -{len(g['removed'])} ~{len(g['changed'])}")
    lines.append(f"  {counts}")

    for k in sorted(p["added"]):
        v = p["added"][k]
        val = v.get("value") if isinstance(v, dict) and "value" in v else v
        lines.append(f"  + param {k} = {fmt_value(val.get('defaultValue')) if isinstance(val, dict) else fmt_value(val)}")
    for r in p["removed"]:
        key = r if isinstance(r, str) else r.get("key")
        lines.append(f"  - param {key}")
    for ch in p["changed"]:
        lines.extend(drill_param_change(ch))

    for ca in c["added"]:
        lines.append(f"  + condition {ca.get('name')!r} ({ca.get('expression')})")
    for cr in c["removed"]:
        lines.append(f"  - condition {cr.get('name')!r}")
    for ch in c["changed"]:
        lines.extend(drill_condition_change(ch))

    # parameterGroups (summary only)
    for ga in g["added"]:
        lines.append(f"  + parameterGroup {ga.get('group')}")
    for gr in g["removed"]:
        lines.append(f"  - parameterGroup {gr}")
    for gc in g["changed"]:
        ip = gc["parameters"]
        lines.append(f"  ~ parameterGroup {gc['group']}: "
                     f"+{len(ip['added'])} -{len(ip['removed'])} ~{len(ip['changed'])}")

    # experiment overlap summary
    summary = d.get("experiment_overlap_summary") or []
    if summary:
        lines.append("")
        lines.append("  Experiment overlaps in window:")
        for s in summary:
            exps = ", ".join((e.get("displayName") or e.get("name")) + f" [{e.get('state')}]"
                             for e in s["experiments"])
            lines.append(f"    {s['type']} {s['target']!r}: {exps}")

    return "\n".join(lines)

def main():
    mode = sys.argv[1]
    with open(sys.argv[2]) as f:
        data = json.load(f)
    if mode == "diff":
        print(render_diff(data))
    elif mode == "changelog":
        blocks = []
        for entry in data:
            if entry.get("is_empty"):
                continue
            blocks.append(render_diff(entry["diff"]))
        if not blocks:
            print("(no non-empty transitions in window)")
        else:
            print("\n\n".join(blocks))
    else:
        print(f"unknown mode: {mode}", file=sys.stderr); sys.exit(2)

if __name__ == "__main__": main()
