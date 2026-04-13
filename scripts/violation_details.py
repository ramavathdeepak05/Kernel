import sqlite3
import os

db_path = r"c:\alis-antigravity\ALIS Production\.code-review-graph\graph.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

query = """
SELECT a.source_qualified, a.target_qualified, a.line, b.line
FROM edges a
JOIN edges b ON (a.source_qualified = b.target_qualified AND a.target_qualified = b.source_qualified)
             OR (a.source_qualified = b.source_qualified AND a.target_qualified = b.target_qualified AND a.id != b.id)
WHERE a.kind = 'IMPORTS_FROM' AND b.kind = 'IMPORTS_FROM'
"""
cur.execute(query)
res = cur.fetchall()

seen = set()
for r in res:
    pair = tuple(sorted([r[0], r[1]]))
    if pair not in seen:
        print(f"{os.path.basename(pair[0])} <--> {os.path.basename(pair[1])} | Lines: {r[2]}, {r[3]}")
        seen.add(pair)
