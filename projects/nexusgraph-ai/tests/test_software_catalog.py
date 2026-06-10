import unittest

import pandas as pd

from src.software_catalog import build_software_catalog


class SoftwareCatalogTests(unittest.TestCase):
    def setUp(self):
        self.nodes = pd.read_csv("graph/nodes.csv")
        self.edges = pd.read_csv("graph/edges.csv")

    def test_catalog_includes_every_service(self):
        catalog = build_software_catalog(self.nodes, self.edges)
        service_count = len(self.nodes[self.nodes["label"] == "Service"])

        self.assertEqual(len(catalog), service_count)

    def test_catalog_uses_internal_and_external_ownership(self):
        catalog = build_software_catalog(self.nodes, self.edges)
        owners_by_service = dict(zip(catalog["Service"], catalog["Owner"]))

        self.assertIn("Platform Engineering", owners_by_service["playback-service"])
        self.assertIn("streaming-platform-team", owners_by_service["playback-service"])
        self.assertEqual(owners_by_service["auth-service"], "identity-platform-team")

    def test_catalog_has_runbook_for_every_service(self):
        catalog = build_software_catalog(self.nodes, self.edges)

        self.assertFalse((catalog["Runbook"] == "Not modeled").any())

    def test_catalog_has_dashboard_for_every_service(self):
        catalog = build_software_catalog(self.nodes, self.edges)

        self.assertFalse((catalog["Dashboard"] == "Not modeled").any())


if __name__ == "__main__":
    unittest.main()
