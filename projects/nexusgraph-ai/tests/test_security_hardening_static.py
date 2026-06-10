from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SecurityHardeningStaticTests(unittest.TestCase):
    def test_docker_ports_bind_to_localhost_only(self):
        compose = (ROOT / "docker-compose.yml").read_text()

        self.assertIn('"127.0.0.1:7474:7474"', compose)
        self.assertIn('"127.0.0.1:7687:7687"', compose)
        self.assertIn('"127.0.0.1:8501:8501"', compose)
        self.assertIn('"127.0.0.1:11434:11434"', compose)
        self.assertNotIn('"7474:7474"', compose)
        self.assertNotIn('"7687:7687"', compose)
        self.assertNotIn('"8501:8501"', compose)
        self.assertNotIn('"11434:11434"', compose)

    def test_streamlit_query_input_has_length_cap(self):
        app = (ROOT / "app" / "streamlit_app.py").read_text()

        self.assertIn("MAX_QUERY_LENGTH = 500", app)
        self.assertIn("max_chars=MAX_QUERY_LENGTH", app)
        self.assertIn("len(user_query) <= MAX_QUERY_LENGTH", app)

    def test_docker_build_context_excludes_local_sensitive_state(self):
        dockerignore = (ROOT / ".dockerignore").read_text()

        self.assertIn(".env", dockerignore)
        self.assertIn("vector_store/", dockerignore)
        self.assertIn(".ruflo/", dockerignore)
        self.assertIn("lib/", dockerignore)


if __name__ == "__main__":
    unittest.main()
