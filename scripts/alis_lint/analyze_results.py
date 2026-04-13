import json

with open("scripts/alis_lint/scan_results.json", "r", encoding="utf-8-sig") as f:
    d = json.load(f)

inv1 = [v for v in d["violations"] if v["rule"] == "INV-1"]
print(f"{len(inv1)} INV-1 violations:")
for v in inv1:
    print(f"  {v['file']}:{v['line']} — {v['message']}")

print(f"\n{len([v for v in d['violations'] if v['rule'] == 'INV-2'])} INV-2 violations")

# Group INV-2 by file
inv2_files = {}
for v in d["violations"]:
    if v["rule"] == "INV-2":
        inv2_files.setdefault(v["file"], []).append(v)
print(f"Spread across {len(inv2_files)} files")
for f, vs in sorted(inv2_files.items()):
    print(f"  {f}: {len(vs)}")
