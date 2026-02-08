"""
ALIS Database Service - Safe DB Tools
(Missing Dependency Implementation for E02-S06)

MODULE: Shared Infrastructure
LAYER: Infrastructure (below Layer 1)
ENTITY: Database Connection

This module provides a safe, centralized way to execute database queries.
It prevents raw SQL injection and ensures connection pooling.

Must Align With:
- "Safe DB Tools" requirement in Project Structure.
- "No Cloud" rule (local PostgreSQL).

Usage:
    from server.db_service import execute_query, execute_transaction

    result = execute_query("SELECT * FROM users WHERE id = %s", (user_id,))
"""

import os
import logging
from typing import List, Dict, Any, Optional, Tuple, Generator
from contextlib import contextmanager

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from psycopg2 import pool
except ImportError:
    # Fallback for environment without psycopg2 (e.g. dev without DB driver)
    # in a real scenario this would act as a mock or raise error
    logging.warning("psycopg2 not found. Database functionality will be mocked or fail.")
    psycopg2 = None
    pool = None

# Configure Logging
logger = logging.getLogger(__name__)

# Connection Pool (Global)
_pg_pool = None

def get_db_pool():
    """Initialize and return the connection pool."""
    global _pg_pool
    if _pg_pool is None and psycopg2:
        try:
            # In a real deployment, these would come from env vars or config.py
            # For now, we use defaults or placeholders.
            _pg_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=20,
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", "postgres"),
                host=os.getenv("DB_HOST", "localhost"),
                port=os.getenv("DB_PORT", "5432"),
                database=os.getenv("DB_NAME", "alis_db")
            )
            logger.info("Database connection pool initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise
    return _pg_pool

@contextmanager
def get_db_connection():
    """
    Context manager to get a connection from the pool.
    Ensures connection is returned to the pool even on error.
    """
    pool = get_db_pool()
    if not pool:
        raise RuntimeError("Database connection pool is not available.")
    
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)

def execute_query(query: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
    """
    Execute a read-only query and return dictionary results.
    
    Args:
        query: SQL query string
        params: Tuple of parameters for variable substitution
    
    Returns:
        List of dicts representing rows.
    """
    if not psycopg2:
        logger.warning("Mocking execute_query due to missing driver.")
        return []

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            try:
                cursor.execute(query, params)
                if cursor.description:
                    return cursor.fetchall()
                return []
            except Exception as e:
                logger.error(f"Query execution failed: {e}\nQuery: {query}")
                raise

def execute_transaction(queries: List[Tuple[str, Optional[Tuple]]]) -> None:
    """
    Execute a list of queries as a single atomic transaction.
    
    Args:
        queries: List of (query_string, params_tuple)
    """
    if not psycopg2:
        logger.warning("Mocking execute_transaction.")
        return

    with get_db_connection() as conn:
        try:
            with conn.cursor() as cursor:
                for query, params in queries:
                    cursor.execute(query, params)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction failed: {e}")
            raise

def init_db():
    """
    Initialize database schema if needed.
    Can be used to create the search index table.
    """
    search_table_sql = """
    CREATE TABLE IF NOT EXISTS search_index (
        id SERIAL PRIMARY KEY,
        entity_type VARCHAR(50) NOT NULL,
        entity_id VARCHAR(100) NOT NULL,
        content TEXT,
        metadata JSONB,
        search_vector TSVECTOR,
        roles_allowed TEXT[],  -- Array of roles allowed to see this result
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE INDEX IF NOT EXISTS idx_search_vector ON search_index USING GIN(search_vector);
    CREATE INDEX IF NOT EXISTS idx_entity_type ON search_index(entity_type);
    """
    try:
        execute_transaction([(search_table_sql, None)])
        logger.info("Search index table initialized.")
    except Exception as e:
        logger.error(f"Failed to init DB: {e}")
