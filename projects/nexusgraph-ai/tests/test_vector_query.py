import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from src import vector_query


class VectorQueryTests(unittest.TestCase):
    def setUp(self):
        vector_query.get_vector_store.cache_clear()

    def tearDown(self):
        vector_query.get_vector_store.cache_clear()

    def test_concurrent_queries_share_one_embedding_model(self):
        init_count = 0
        init_lock = threading.Lock()

        class FakeEmbeddings:
            def __init__(self, model_name):
                nonlocal init_count
                with init_lock:
                    init_count += 1

        class FakeDoc:
            id = "doc-1"
            metadata = {"source": "test"}
            page_content = "test document"

        class FakeChroma:
            def __init__(self, collection_name, embedding_function, persist_directory):
                self.collection_name = collection_name
                self.embedding_function = embedding_function
                self.persist_directory = persist_directory

            def similarity_search_with_score(self, query, k):
                return [(FakeDoc(), 0.1)]

        with patch.object(vector_query, "HuggingFaceEmbeddings", FakeEmbeddings), \
             patch.object(vector_query, "Chroma", FakeChroma):
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(
                    lambda _: vector_query.query_vector_store(
                        "query",
                        persist_path=Path("."),
                        collection_name="test",
                    ),
                    range(8),
                ))

        self.assertEqual(init_count, 1)
        self.assertEqual(len(results), 8)


if __name__ == "__main__":
    unittest.main()
