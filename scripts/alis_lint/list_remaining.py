import json
from pathlib import Path

with open("scripts/alis_lint/scan_latest.json", "r", encoding="utf-8-sig") as f:
    data = json.load(f)

for v in data["violations"]:
    msg = v["message"].split("()")[0] if "()" in v["message"] else v["message"][:60]
    print(f"{v['rule']} | {v['file']}:{v['line']} | {msg}")
