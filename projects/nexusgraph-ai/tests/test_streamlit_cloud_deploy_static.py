from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StreamlitCloudDeployStaticTests(unittest.TestCase):
    def test_entrypoint_directory_has_requirements_shim(self):
        requirements = ROOT / "app" / "requirements.txt"

        self.assertTrue(requirements.exists())
        self.assertEqual(requirements.read_text().strip(), "-r ../requirements.txt")

    def test_app_hydrates_streamlit_secrets_before_backend_imports(self):
        source = (ROOT / "app" / "streamlit_app.py").read_text()

        hydrate_index = source.index("hydrate_streamlit_secrets()")
        backend_import_index = source.index("from hybrid_rag import run_graph_rag, run_vector_rag")
        self.assertLess(hydrate_index, backend_import_index)

    def test_app_ensures_vector_store_for_streamlit_cloud(self):
        source = (ROOT / "app" / "streamlit_app.py").read_text()

        self.assertIn("def ensure_runtime_data()", source)
        self.assertIn("ingest_documents()", source)
        self.assertIn("NEXUSGRAPH_AUTO_IMPORT_NEO4J", source)


if __name__ == "__main__":
    unittest.main()
