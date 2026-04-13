import sqlite3
import pprint
conn = sqlite3.connect(r'c:\alis-antigravity\ALIS Production\.code-review-graph\graph.db')
cur = conn.cursor()
cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
tables = cur.fetchall()
for t in tables:
    print(t[0])
    print(t[1])
    print('-'*40)
conn.close()
