from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StreamlitCloudDeployStaticTests(unittest.TestCase):
    def test_entrypoint_directory_has_requirements_shim(self):
        root_requirements = (ROOT / "requirements.txt").read_text()
        app_requirements = ROOT / "app" / "requirements.txt"

        self.assertTrue(app_requirements.exists())
        self.assertEqual(app_requirements.read_text(), root_requirements)
        self.assertIn("streamlit==", app_requirements.read_text())
        self.assertIn("langchain==", app_requirements.read_text())

    def test_python_runtime_is_pinned_for_streamlit_cloud(self):
        runtime = ROOT / "runtime.txt"
        app_runtime = ROOT / "app" / "runtime.txt"

        self.assertTrue(runtime.exists())
        self.assertTrue(app_runtime.exists())
        self.assertEqual(runtime.read_text().strip(), "python-3.12")
        self.assertEqual(app_runtime.read_text().strip(), "python-3.12")

    def test_app_hydrates_streamlit_secrets_before_backend_imports(self):
        source = (ROOT / "app" / "streamlit_app.py").read_text()

        hydrate_index = source.index("hydrate_streamlit_secrets()")
        backend_import_index = source.index("def load_rag_runners()")
        self.assertLess(hydrate_index, backend_import_index)

    def test_app_does_not_import_neo4j_backend_at_module_load(self):
        source = (ROOT / "app" / "streamlit_app.py").read_text()

        self.assertNotIn("from hybrid_rag import run_graph_rag, run_vector_rag", source)
        self.assertIn("def load_rag_runners()", source)
        self.assertIn("from hybrid_rag import (", source)

    def test_app_ensures_vector_store_for_streamlit_cloud(self):
        source = (ROOT / "app" / "streamlit_app.py").read_text()

        self.assertIn("def ensure_runtime_data()", source)
        self.assertIn("from seed_runtime_data import seed_all", source)
        self.assertIn("seed_all(", source)
        self.assertIn("NEXUSGRAPH_AUTO_IMPORT_NEO4J", source)
        self.assertIn('env_flag("NEXUSGRAPH_FORCE_VECTOR_SEED", True)', source)

    def test_neo4j_import_script_loads_dotenv_for_local_aura_checks(self):
        source = (ROOT / "src" / "import_to_neo4j.py").read_text()

        self.assertIn("from dotenv import load_dotenv", source)
        self.assertIn("load_dotenv()", source)

    def test_railway_uses_dockerfile_and_streamlit_healthcheck(self):
        config = tomllib.loads((ROOT / "railway.toml").read_text())

        self.assertEqual(config["build"]["builder"], "DOCKERFILE")
        self.assertEqual(config["build"]["dockerfilePath"], "Dockerfile")
        self.assertEqual(config["deploy"]["healthcheckPath"], "/_stcore/health")
        self.assertGreaterEqual(config["deploy"]["healthcheckTimeout"], 300)

    def test_docker_entrypoint_binds_streamlit_to_runtime_port(self):
        entrypoint = (ROOT / "scripts" / "entrypoint.sh").read_text()

        self.assertIn("src/seed_runtime_data.py --neo4j --force-vector", entrypoint)
        self.assertIn("PORT:-8501", entrypoint)
        self.assertIn("--server.address=0.0.0.0", entrypoint)
        self.assertIn("--server.port=${APP_PORT}", entrypoint)


if __name__ == "__main__":
    unittest.main()
