"""
Unit Tests for Global Search Service (E02-S06)
"""

import unittest
from unittest.mock import patch, MagicMock
from server.mcp.search_service import index_entity, search, SearchEntityType, SearchResult
from server.core.rbac import Role

class TestSearchService(unittest.TestCase):

    @patch('server.mcp.search_service.execute_transaction')
    def test_index_entity(self, mock_exec_trans):
        """Test indexing an entity."""
        index_entity(
            entity_type=SearchEntityType.USER,
            entity_id="user-123",
            content="John Doe Student",
            metadata={"department": "CS"},
            roles_allowed=[Role.ADMIN, Role.FACULTY]
        )
        
        # Verify transaction called with DELETE and INSERT ops
        self.assertTrue(mock_exec_trans.called)
        args, _ = mock_exec_trans.call_args
        queries = args[0]
        self.assertEqual(len(queries), 2)
        self.assertIn("INSERT INTO search_index", queries[1][0])

    @patch('server.mcp.search_service.execute_query')
    def test_search_rbac_filtering(self, mock_exec_query):
        """Test search query execution."""
        # Mock DB return
        mock_exec_query.return_value = [{
            'entity_type': 'user',
            'entity_id': 'user-123',
            'snippet': '<b>John</b> Doe',
            'relevance': 0.8,
            'metadata': '{"department": "CS"}'
        }]

        results = search("John", Role.STUDENT)
        
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], SearchResult)
        self.assertEqual(results[0].entity_id, "user-123")
        
        # Verify query structure
        args, _ = mock_exec_query.call_args
        query_sql = args[0]
        self.assertIn("search_vector @@ to_tsquery", query_sql)
        self.assertIn("student", args[1]) # Verify role is passed correctly

if __name__ == '__main__':
    unittest.main()
