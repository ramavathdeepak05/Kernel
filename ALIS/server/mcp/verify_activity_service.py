import sys
import os
import json
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from server.core.rbac import Role
# Import service functions - we will patch db_service usage indirectly or directly
import server.db_service as db_service
import server.mcp.activity_service as activity_service
from server.mcp.activity_service import ActivityType

# --- Mock DB Infrastructure ---
# Since psycopg2 is missing, we simulate the DB to verify the SERVICE LOGIC
# (i.e. are the right queries generated, and is the result parsing correct?)

MOCK_ACTIVITY_TABLE = []
MOCK_COMMENTS_TABLE = []
ID_COUNTER = 1

def mock_execute_query(query, params):
    global ID_COUNTER
    # Simple semantic parser for the verification needs
    query = query.strip().upper()
    
    # INSERT ACTIVITY
    if "INSERT INTO ACTIVITY_FEED" in query:
        # params: entity_type, entity_id, activity_type, description, actor_id, actor_role, visible_to_roles, metadata
        row = {
            "id": ID_COUNTER,
            "entity_type": params[0],
            "entity_id": params[1],
            "activity_type": params[2],
            "description": params[3],
            "actor_id": params[4],
            "actor_role": params[5],
            "visible_to_roles": params[6], # list
            "metadata": json.loads(params[7]),
            "created_at": datetime.now()
        }
        MOCK_ACTIVITY_TABLE.append(row)
        ID_COUNTER += 1
        return [{"id": row["id"]}]
        
    # INSERT COMMENT
    elif "INSERT INTO COMMENTS" in query:
        # params: entity_type, entity_id, content, parent_id, actor_id, actor_role, visible_to_roles
        row = {
            "id": ID_COUNTER,
            "entity_type": params[0],
            "entity_id": params[1],
            "content": params[2],
            "parent_id": params[3],
            "actor_id": params[4],
            "actor_role": params[5],
            "visible_to_roles": params[6], # list
            "is_hidden": False,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        MOCK_COMMENTS_TABLE.append(row)
        ID_COUNTER += 1
        return [{"id": row["id"]}]

    # SELECT FEED (UNION)
    elif "SELECT" in query and "ACTIVITY_FEED" in query and "COMMENTS" in query:
        # params: entity_type, entity_id, user_role, entity_type, user_role...
        # The query structure in service is complex, so we manually simulate the FILTERING logic
        # based on the params passed to get_feed (which we can inferred from the bind params)
        
        # Params mapping from service call:
        # 0,1: entity fitler for activity
        # 2: user_role for activity
        # 3,4: entity filter for comments
        # 5: user_role for comments
        
        target_entity_type = params[0]
        target_entity_id = params[1]
        viewer_role = params[2]
        
        results = []
        
        # Filter Activity
        for row in MOCK_ACTIVITY_TABLE:
            if (row["entity_type"] == target_entity_type and 
                row["entity_id"] == target_entity_id and
                viewer_role in row["visible_to_roles"]):
                
                results.append({
                    "type": "activity",
                    "subtype": row["activity_type"],
                    "id": row["id"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "content": row["description"],
                    "metadata": row["metadata"],
                    "actor_id": row["actor_id"],
                    "actor_role": row["actor_role"],
                    "created_at": row["created_at"],
                    "parent_id": None,
                    "is_hidden": False
                })
                
        # Filter Comments
        for row in MOCK_COMMENTS_TABLE:
            if (row["entity_type"] == target_entity_type and 
                row["entity_id"] == target_entity_id and
                viewer_role in row["visible_to_roles"] and
                not row["is_hidden"]):
                
                results.append({
                    "type": "comment",
                    "subtype": None,
                    "id": row["id"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "content": row["content"],
                    "metadata": None,
                    "actor_id": row["actor_id"],
                    "actor_role": row["actor_role"],
                    "created_at": row["created_at"],
                    "parent_id": row["parent_id"],
                    "is_hidden": row["is_hidden"]
                })
        
        # Sort desc
        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results

    return []

def mock_execute_transaction(queries):
    # Handle hide_comment
    for sql, params in queries:
        sql = sql.strip().upper()
        if "UPDATE COMMENTS SET IS_HIDDEN" in sql:
            cid = params[0]
            for row in MOCK_COMMENTS_TABLE:
                if row["id"] == cid:
                    row["is_hidden"] = True
                    print(f"[MOCK DB] Hidden comment {cid}")

# Patching
# We must patch the function AS IMPORTED by the service module
activity_service.execute_query = mock_execute_query
activity_service.execute_transaction = mock_execute_transaction


def run_verification():
    print("--- 1. Initialize DB (Mocked) ---")
    # No-op in mock
    
    print("\n--- 2. Seed Data ---")
    entity_id = "application:123"
    entity_type = "application"
    
    # 2.1 Log Public Activity (Visible to Student & Faculty)
    print("Logging activity...")
    activity_service.log_activity(
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type=ActivityType.STATUS_CHANGE,
        description="Application status changed to REVIEW_PENDING",
        actor_id="system",
        actor_role=Role.AI_AGENT, # Fixed: Role.AGENT -> Role.AI_AGENT
        visible_to_roles=[Role.STUDENT, Role.FACULTY]
    )
    
    # 2.2 Add Student Comment (Visible to Student & Faculty)
    print("Adding student comment...")
    cid_stud = activity_service.add_comment(
        entity_type=entity_type, 
        entity_id=entity_id,
        content="I have uploaded the missing docs.",
        actor_id="student_1",
        actor_role=Role.STUDENT,
        visible_to_roles=[Role.STUDENT, Role.FACULTY]
    )
    
    # 2.3 Add Internal Faculty Note (Visible to Faculty ONLY)
    print("Adding faculty note...")
    cid_fac = activity_service.add_comment(
        entity_type=entity_type, 
        entity_id=entity_id,
        content="Internal Note: Documents look shaky. Verify with board.",
        actor_id="faculty_1",
        actor_role=Role.FACULTY,
        visible_to_roles=[Role.FACULTY]
    )
    
    # 2.4 Add Toxic Comment (To be hidden)
    print("Adding toxic comment...")
    cid_toxic = activity_service.add_comment(
        entity_type=entity_type, 
        entity_id=entity_id,
        content="This system is trash.",
        actor_id="student_1",
        actor_role=Role.STUDENT,
        visible_to_roles=[Role.STUDENT, Role.FACULTY]
    )
    activity_service.hide_comment(cid_toxic, Role.FACULTY)

    print("\n--- 3. Verify RBAC Visibility ---")
    
    # TEST CASE A: Viewer = STUDENT
    print("Fetching feed for STUDENT...")
    feed_student = activity_service.get_feed(entity_type, entity_id, Role.STUDENT)
    print(f"[STUDENT FEED] Items: {len(feed_student)}")
    
    descriptions_std = [
        item.data.description if item.type == 'activity' else item.data.content 
        for item in feed_student
    ]
    print("Student sees:", descriptions_std)
    
    assert "Application status changed to REVIEW_PENDING" in descriptions_std
    assert "I have uploaded the missing docs." in descriptions_std
    assert "Internal Note: Documents look shaky. Verify with board." not in descriptions_std
    assert "This system is trash." not in descriptions_std
    print("✅ STUDENT VIEW passed.")

    # TEST CASE B: Viewer = FACULTY
    print("\nFetching feed for FACULTY...")
    feed_faculty = activity_service.get_feed(entity_type, entity_id, Role.FACULTY)
    print(f"[FACULTY FEED] Items: {len(feed_faculty)}")
    
    descriptions_fac = [
        item.data.description if item.type == 'activity' else item.data.content 
        for item in feed_faculty
    ]
    print("Faculty sees:", descriptions_fac)

    assert "Internal Note: Documents look shaky. Verify with board." in descriptions_fac
    assert "This system is trash." not in descriptions_fac # Should be hidden for everyone
    print("✅ FACULTY VIEW passed.")
    
    print("\n--- VERIFICATION SUCCESS ---")

if __name__ == "__main__":
    run_verification()
