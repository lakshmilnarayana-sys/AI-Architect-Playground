import unittest

from src.vector_ingest import build_ingestion_documents


class VectorIngestionTests(unittest.TestCase):
    def test_builds_documents_from_graph_and_source_artifacts(self):
        documents = build_ingestion_documents()

        ids = {doc["id"] for doc in documents}
        sources = {doc["metadata"]["source"] for doc in documents}

        self.assertIn("graph-node-service-playback", ids)
        self.assertIn("graph-edge-service-playback-depends-on-service-manifest", ids)
        self.assertIn("data-runbooks-yaml", ids)
        self.assertIn("graph/nodes.csv", sources)
        self.assertIn("graph/edges.csv", sources)
        self.assertIn("data/runbooks.yaml", sources)

    def test_documents_have_non_empty_text_and_metadata(self):
        documents = build_ingestion_documents()

        self.assertGreater(len(documents), 300)
        for doc in documents:
            self.assertTrue(doc["id"])
            self.assertTrue(doc["text"].strip())
            self.assertIn("source", doc["metadata"])
            self.assertIn("kind", doc["metadata"])


if __name__ == "__main__":
    unittest.main()
