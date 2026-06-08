import unittest
from pathlib import Path
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

ROOT = Path(__file__).resolve().parents[1]
CHROMA_PATH = ROOT / 'vector_store' / 'chroma'
COLLECTION_NAME = 'nexusgraph_ai_knowledge'

class VectorRetrievalTests(unittest.TestCase):
    def test_retrieval_works(self):
        embeddings = HuggingFaceEmbeddings(model_name='sentence-transformers/all-MiniLM-L6-v2')
        vector_store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=str(CHROMA_PATH),
        )
        
        query = "What is the playback service?"
        results = vector_store.similarity_search(query, k=3)
        
        self.assertGreater(len(results), 0)
        # Check if playback service is in the results
        texts = [doc.page_content.lower() for doc in results]
        found_playback = any("playback" in text for text in texts)
        self.assertTrue(found_playback, f"Playback not found in results: {texts}")

if __name__ == "__main__":
    unittest.main()
