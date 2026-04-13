"""
Re-scan graph.db lateral violations post-fix.
Run this after code changes to verify 0 lateral violations remain.
"""
import sqlite3
import re
from collections import defaultdict

DB = r".code-review-graph\graph.db"
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

SERVER_RE = re.compile(r'ALIS[\\/]server[\\/](\w+)[\\/]')
INFRA = {"core", "db_service", "api", "tasks", "rules", "agents", "tools",
         "integrations", "migrations", "communication"}

rows = db.execute("""
    SELECT kind, source_qualified, target_qualified, file_path, line
    FROM edges
    WHERE kind IN ('CALLS', 'IMPORTS_FROM', 'IMPORTS')
""").fetchall()

lateral = defaultdict(list)
for r in rows:
    src = SERVER_RE.search(r["source_qualified"] or "")
    tgt = SERVER_RE.search(r["target_qualified"] or "")
    if not src or not tgt:
        continue
    sm, tm = src.group(1), tgt.group(1)
    if sm == tm or sm in INFRA or tm in INFRA:
        continue
    lateral[(sm, tm)].append(r)

if not lateral:
    print("✓ Zero lateral violations detected in graph.db")
else:
    print(f"⚠ {sum(len(v) for v in lateral.values())} lateral violations remain:")
    for (src, tgt), calls in sorted(lateral.items(), key=lambda x: -len(x[1])):
        print(f"  {src} -> {tgt} ({len(calls)})")
        seen = set()
        for r in calls:
            c = (r["source_qualified"], r["target_qualified"])
            if c not in seen:
                seen.add(c)
                print(f"    [{r['kind']}] …{r['source_qualified'][-60:]} -> …{r['target_qualified'][-60:]} L{r['line']}")
