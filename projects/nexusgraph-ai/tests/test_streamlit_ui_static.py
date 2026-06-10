from pathlib import Path
import unittest


APP_SOURCE = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


class StreamlitUiStaticTests(unittest.TestCase):
    def test_json_response_sections_are_collapsed_by_default(self):
        source = APP_SOURCE.read_text()

        self.assertIn('st.expander("JSON response", expanded=False)', source)
        self.assertNotIn('st.tabs(["JSON response", "Behind the scenes"])', source)

    def test_pyvis_graph_uses_remote_assets_without_writing_lib_directory(self):
        source = APP_SOURCE.read_text()

        self.assertIn("cdn_resources='remote'", source)
        self.assertIn("net.generate_html", source)
        self.assertNotIn("net.save_graph", source)

    def test_backend_errors_are_summarized_before_display(self):
        source = APP_SOURCE.read_text()

        self.assertIn("def summarize_backend_error", source)
        self.assertIn("resource_exhausted", source)
        self.assertIn("summarize_backend_error(e)", source)
        self.assertNotIn('{"answer": None, "error": str(e)', source)


if __name__ == "__main__":
    unittest.main()
