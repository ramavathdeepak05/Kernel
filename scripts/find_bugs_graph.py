import sqlite3
import os
import json

db_path = r"c:\alis-antigravity\ALIS Production\.code-review-graph\graph.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

output = {"nested_transactions": [], "celery_db_calls": [], "dead_code": []}

def run_queries():
    cur.execute("""
    WITH transaction_callers AS (
        SELECT DISTINCT e1.source_qualified 
        FROM edges e1 
        WHERE e1.target_qualified LIKE '%execute_transaction%' AND e1.kind = 'CALLS'
    )
    SELECT tc1.source_qualified, e.target_qualified, e.line
    FROM edges e
    JOIN transaction_callers tc1 ON e.source_qualified = tc1.source_qualified
    JOIN transaction_callers tc2 ON e.target_qualified = tc2.source_qualified
    WHERE e.kind = 'CALLS'
    """)
    for r in cur.fetchall():
        if r[0] != r[1]:
            output["nested_transactions"].append({"caller": r[0], "callee": r[1], "line": r[2]})

    cur.execute("""
    SELECT e.source_qualified, e.target_qualified, e.line 
    FROM edges e 
    WHERE e.source_qualified LIKE '%tasks.%' 
      AND (e.target_qualified LIKE '%execute_query%' OR e.target_qualified LIKE '%execute_transaction%')
      AND e.kind = 'CALLS'
      AND e.target_qualified NOT LIKE '%system%'
    """)
    for r in cur.fetchall():
        output["celery_db_calls"].append({"caller": r[0], "callee": r[1], "line": r[2]})

    cur.execute("""
    SELECT n.qualified_name, n.file_path 
    FROM nodes n
    LEFT JOIN edges e ON n.qualified_name = e.target_qualified AND e.kind IN ('CALLS', 'IMPORTS_FROM', 'INSTANTIATES')
    WHERE e.id IS NULL 
      AND n.kind IN ('FUNCTION', 'CLASS')
      AND n.file_path NOT LIKE '%test%'
      AND n.qualified_name NOT LIKE '%__init__%'
      AND n.qualified_name NOT LIKE '%__main__%'
      AND n.qualified_name NOT LIKE 'alembic%'
    LIMIT 20
    """)
    for r in cur.fetchall():
        output["dead_code"].append({"name": r[0], "file": r[1]})
        
        
    # --- 4. Missing Audit Logs ---
    # Find functions that call execute_transaction but do NOT call AuditLog
    cur.execute("""
    WITH transaction_callers AS (
        SELECT DISTINCT source_qualified
        FROM edges
        WHERE target_qualified LIKE '%execute_transaction%' AND kind = 'CALLS'
    ),
    audit_callers AS (
        SELECT DISTINCT source_qualified
        FROM edges
        WHERE target_qualified LIKE '%AuditLog%' AND kind = 'CALLS'
    )
    SELECT t.source_qualified
    FROM transaction_callers t
    LEFT JOIN audit_callers a ON t.source_qualified = a.source_qualified
    WHERE a.source_qualified IS NULL
      AND t.source_qualified NOT LIKE '%test%'
      AND t.source_qualified NOT LIKE '%Audit%'
      AND t.source_qualified NOT LIKE '%domain_events%'
      AND t.source_qualified NOT LIKE '%alembic%'
    LIMIT 20
    """)
    output["missing_audit_logs"] = [r[0] for r in cur.fetchall()]

    # --- 5. Mutations using execute_query (Read-Only) ---
    cur.execute("""
    SELECT DISTINCT e.source_qualified
    FROM edges e
    WHERE e.target_qualified LIKE '%execute_query%' AND e.kind = 'CALLS'
      AND (e.source_qualified LIKE '%create_%' 
           OR e.source_qualified LIKE '%update_%' 
           OR e.source_qualified LIKE '%delete_%'
           OR e.source_qualified LIKE '%insert_%')
      AND e.source_qualified NOT LIKE '%test%'
    LIMIT 20
    """)
    output["mutations_using_execute_query"] = [r[0] for r in cur.fetchall()]

    with open("bugs.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

if __name__ == "__main__":
    run_queries()
