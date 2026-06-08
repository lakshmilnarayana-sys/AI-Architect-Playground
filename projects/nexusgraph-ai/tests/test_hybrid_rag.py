import unittest
from src.hybrid_rag import app

class HybridRagTests(unittest.TestCase):
    def test_router_vector_flow(self):
        # Descriptive query should favor vector
        query = "What is the nexusgraph-ai project?"
        inputs = {"query": query, "context": []}
        
        nodes_visited = []
        for output in app.stream(inputs):
            for key in output.keys():
                nodes_visited.append(key)
        
        self.assertIn("router", nodes_visited)
        self.assertIn("vector_node", nodes_visited)
        self.assertIn("synthesizer_node", nodes_visited)

    def test_router_graph_flow(self):
        # Relationship query should favor graph
        query = "How is Emma Chen related to the playback service?"
        inputs = {"query": query, "context": []}
        
        nodes_visited = []
        for output in app.stream(inputs):
            for key in output.keys():
                nodes_visited.append(key)
        
        self.assertIn("router", nodes_visited)
        self.assertIn("graph_node", nodes_visited)
        self.assertIn("synthesizer_node", nodes_visited)

if __name__ == "__main__":
    unittest.main()
