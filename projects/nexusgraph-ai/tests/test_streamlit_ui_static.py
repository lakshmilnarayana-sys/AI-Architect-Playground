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


if __name__ == "__main__":
    unittest.main()
