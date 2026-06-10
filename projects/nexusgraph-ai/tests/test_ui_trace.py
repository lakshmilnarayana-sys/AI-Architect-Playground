import unittest

from src.ui_trace import evidence_counts, format_stage_elapsed


class UiTraceTests(unittest.TestCase):
    def test_format_stage_elapsed_handles_missing_time(self):
        self.assertEqual(format_stage_elapsed({}), "not timed")

    def test_format_stage_elapsed_formats_seconds(self):
        self.assertEqual(format_stage_elapsed({"elapsed": 1.234}), "1.23s")

    def test_evidence_counts(self):
        trace = {
            "evidence": {
                "vector": [{}, {}],
                "graph": [{}],
                "merged": [{}],
            }
        }
        self.assertEqual(evidence_counts(trace), {"vector": 2, "graph": 1, "merged": 1})


if __name__ == "__main__":
    unittest.main()
