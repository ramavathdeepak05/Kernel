import sqlite3
import json

conn = sqlite3.connect(r'c:\alis-antigravity\ALIS Production\.code-review-graph\graph.db')
cur = conn.cursor()
cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
tables = cur.fetchall()

result = []
for t in tables:
    result.append({"table": t[0], "schema": t[1]})

# Also get first few edges to see what relations exist
try:
    cur.execute("SELECT * FROM edges LIMIT 5")
    edges_rows = cur.fetchall()
    cur.execute("PRAGMA table_info(edges)")
    edges_cols = [x[1] for x in cur.fetchall()]
    edges_data = [dict(zip(edges_cols, row)) for row in edges_rows]
except Exception as e:
    edges_data = str(e)

conn.close()

with open(r'c:\alis-antigravity\ALIS Production\scripts\schema_dump.json', 'w') as f:
    json.dump({'schema': result, 'sample_edges': edges_data}, f, indent=2)
