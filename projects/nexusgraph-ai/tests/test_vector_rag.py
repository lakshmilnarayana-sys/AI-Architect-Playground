import unittest

from src.vector_rag import synthesize_answer


class VectorRagTests(unittest.TestCase):
    def test_synthesizes_readable_answer_with_citations(self):
        result = synthesize_answer(
            "Who is on call for playback-service?",
            [
                {
                    "id": "edge-schedule",
                    "document": "Graph relationship: service:playback HAS_ONCALL_SCHEDULE oncall:playback-primary.",
                    "metadata": {"source": "graph/edges.csv", "kind": "graph_edge"},
                    "distance": 0.7,
                },
                {
                    "id": "edge-primary",
                    "document": "Graph relationship: oncall:playback-primary CURRENT_PRIMARY_ONCALL person:emma-chen.",
                    "metadata": {"source": "graph/edges.csv", "kind": "graph_edge"},
                    "distance": 0.9,
                },
            ],
        )

        self.assertIn("Vector RAG answer", result)
        self.assertIn("service:playback HAS_ONCALL_SCHEDULE oncall:playback-primary", result)
        self.assertIn("oncall:playback-primary CURRENT_PRIMARY_ONCALL person:emma-chen", result)
        self.assertIn("Sources", result)
        self.assertIn("graph/edges.csv", result)

    def test_handles_no_matches(self):
        result = synthesize_answer("Unknown question", [])

        self.assertIn("I could not find relevant vector context", result)
        self.assertIn("Unknown question", result)


if __name__ == "__main__":
    unittest.main()
