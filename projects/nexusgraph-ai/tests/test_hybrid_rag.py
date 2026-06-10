import unittest
from unittest.mock import patch

from src import hybrid_rag
from src.hybrid_rag import app

class HybridRagTests(unittest.TestCase):
    def test_make_trace_stage_shape(self):
        stage = hybrid_rag.make_trace_stage(
            name="Vector retrieval",
            status="complete",
            summary="Retrieved 3 chunks",
            elapsed=1.234,
            details={"matches": 3},
        )

        self.assertEqual(stage["name"], "Vector retrieval")
        self.assertEqual(stage["status"], "complete")
        self.assertEqual(stage["summary"], "Retrieved 3 chunks")
        self.assertEqual(stage["elapsed"], 1.234)
        self.assertEqual(stage["details"], {"matches": 3})

    def test_empty_trace_shape(self):
        trace = hybrid_rag.empty_trace("vector")

        self.assertEqual(trace["mode"], "vector")
        self.assertEqual(trace["stages"], [])
        self.assertEqual(trace["evidence"]["vector"], [])
        self.assertEqual(trace["evidence"]["graph"], [])
        self.assertEqual(trace["evidence"]["merged"], [])
        self.assertEqual(trace["known_gaps"], [])

    def test_vector_node_returns_trace_evidence(self):
        with patch.object(
            hybrid_rag,
            "query_vector_store",
            return_value={
                "matches": [
                    {
                        "document": "Runbook node named Billing Incident Runbook.",
                        "distance": 0.12,
                        "metadata": {"source": "graph/nodes.csv", "kind": "graph_node"},
                    }
                ]
            },
        ):
            result = hybrid_rag.vector_node({"query": "billing runbook", "context": []})

        self.assertEqual(len(result["trace"]["stages"]), 1)
        self.assertEqual(result["trace"]["stages"][0]["name"], "Vector retrieval")
        self.assertEqual(result["trace"]["evidence"]["vector"][0]["source"], "graph/nodes.csv")

    def test_graph_node_returns_trace_evidence_for_deterministic_query(self):
        fake_graph = type("Graph", (), {
            "query": lambda self, cypher: [
                {
                    "service": "billing-service",
                    "runbooks": ["Billing Incident Runbook"],
                    "runbook_descriptions": ["Steps for payment anomalies"],
                    "dashboards": ["Billing Health"],
                    "slos": ["Billing Availability"],
                    "schedules": ["Billing Primary On-call"],
                }
            ]
        })()

        with patch.object(hybrid_rag, "graph", fake_graph):
            result = hybrid_rag.graph_node({"query": "What does the billing service runbook cover?", "context": []})

        self.assertEqual(result["trace"]["stages"][0]["name"], "Graph retrieval")
        self.assertEqual(result["trace"]["evidence"]["graph"][0]["row_count"], 1)
        self.assertIn("service:billing", result["trace"]["evidence"]["graph"][0]["cypher"])

    def test_normalizes_openai_style_token_usage(self):
        class Response:
            usage_metadata = None
            response_metadata = {
                "token_usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                }
            }

        self.assertEqual(
            hybrid_rag.extract_token_usage(Response()),
            {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
        )

    def test_run_vector_rag_returns_token_usage(self):
        with patch.object(hybrid_rag, "vector_node", return_value={"context": ["context"]}), \
             patch.object(
                 hybrid_rag,
                 "synthesizer_node",
                 return_value={
                     "answer": "answer",
                     "token_usage": {
                         "input_tokens": 10,
                         "output_tokens": 5,
                         "total_tokens": 15,
                     },
                 },
             ):
            result = hybrid_rag.run_vector_rag("What is playback?")

        self.assertEqual(result["token_usage"]["total_tokens"], 15)

    def test_run_vector_rag_returns_trace(self):
        with patch.object(
            hybrid_rag,
            "vector_node",
            return_value={
                "context": ["Vector Store: context"],
                "trace": {
                    "mode": "vector",
                    "stages": [hybrid_rag.make_trace_stage("Vector retrieval", "complete", "Retrieved 1 chunk")],
                    "evidence": {"vector": [{"source": "data/runbooks.yaml"}], "graph": [], "merged": []},
                    "known_gaps": [],
                },
            },
        ), patch.object(
            hybrid_rag,
            "synthesizer_node",
            return_value={
                "answer": "answer",
                "token_usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            },
        ):
            result = hybrid_rag.run_vector_rag("billing runbook")

        self.assertEqual(result["trace"]["mode"], "vector")
        self.assertEqual(result["trace"]["stages"][0]["name"], "Vector retrieval")

    def test_run_hybrid_rag_returns_merged_trace(self):
        with patch.object(
            hybrid_rag,
            "vector_node",
            return_value={
                "context": ["Vector Store: runbook"],
                "trace": {
                    "mode": "vector",
                    "stages": [hybrid_rag.make_trace_stage("Vector retrieval", "complete", "Retrieved 1 chunk")],
                    "evidence": {"vector": [{"source": "data/runbooks.yaml"}], "graph": [], "merged": []},
                    "known_gaps": [],
                },
            },
        ), patch.object(
            hybrid_rag,
            "graph_node",
            return_value={
                "context": ["Graph Analysis: service has runbook"],
                "trace": {
                    "mode": "graph",
                    "stages": [hybrid_rag.make_trace_stage("Graph retrieval", "complete", "Returned 1 row")],
                    "evidence": {"vector": [], "graph": [{"row_count": 1}], "merged": []},
                    "known_gaps": [],
                },
            },
        ), patch.object(
            hybrid_rag,
            "synthesizer_node",
            return_value={
                "answer": "hybrid answer",
                "token_usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            },
        ):
            result = hybrid_rag.run_hybrid_rag("billing runbook")

        self.assertEqual(result["trace"]["mode"], "hybrid")
        self.assertEqual(len(result["trace"]["evidence"]["vector"]), 1)
        self.assertEqual(len(result["trace"]["evidence"]["graph"]), 1)
        self.assertEqual(result["trace"]["stages"][-1]["name"], "Synthesis")

    def test_hybrid_rag_synthesizes_vector_and_graph_context(self):
        captured_context = []

        def capture_synthesizer(state):
            captured_context.extend(state["context"])
            return {
                "answer": "hybrid answer",
                "token_usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "total_tokens": 2,
                },
            }

        with patch.object(hybrid_rag, "vector_node", return_value={"context": ["Vector Store: runbook context"]}), \
             patch.object(hybrid_rag, "graph_node", return_value={"context": ["Graph Analysis: owner context"]}), \
             patch.object(hybrid_rag, "synthesizer_node", side_effect=capture_synthesizer):
            hybrid_rag.run_hybrid_rag("Who owns playback and what runbook exists?")

        self.assertEqual(
            captured_context,
            ["Vector Store: runbook context", "Graph Analysis: owner context"],
        )

    def test_relationship_cypher_returns_path_relationships(self):
        cypher = (
            "MATCH (p:Person)-[*1..3]-(s:Service) "
            "WHERE p.name =~ '(?i)Emma Chen' AND s.name =~ '(?i)playback.*' "
            "RETURN p.name, s.name, labels(s)"
        )

        enhanced = hybrid_rag.enhance_relationship_cypher(cypher)

        self.assertIn("MATCH path=", enhanced)
        self.assertIn("nodes(path)", enhanced)
        self.assertIn("relationships(path)", enhanced)
        self.assertNotIn("RETURN p.name, s.name, labels(s)", enhanced)

    def test_person_service_cypher_uses_broad_paths_even_with_invented_relationship_types(self):
        cypher = (
            "MATCH (p:Person)-[:USES_SERVICE|OWNS_SERVICE|MAINTAINS_SERVICE]-(s:Service) "
            "WHERE p.name =~ '(?i)Emma Chen' AND s.name =~ '(?i)playback.*' "
            "RETURN p, s"
        )

        enhanced = hybrid_rag.enhance_relationship_cypher(cypher)

        self.assertIn("MATCH path=(p:Person)-[*1..3]-(s:Service)", enhanced)
        self.assertIn("nodes(path)", enhanced)
        self.assertIn("relationships(path)", enhanced)
        self.assertNotIn("USES_SERVICE", enhanced)

    def test_observability_plan_uses_deterministic_graph_query(self):
        cypher = hybrid_rag.deterministic_cypher_for_query("What is the observability unification plan?")

        self.assertIsNotNone(cypher)
        self.assertIn("document:observability-plan", cypher)
        self.assertIn("project:observability-unification", cypher)
        self.assertIn("PRODUCED_DOCUMENT", cypher)

    def test_today_oncall_schedule_returns_all_services(self):
        cypher = hybrid_rag.deterministic_cypher_for_query("what is the oncall-schedule for today?")

        self.assertIsNotNone(cypher)
        self.assertIn("MATCH (service:Service)", cypher)
        self.assertIn("OPTIONAL MATCH (service)-[:HAS_ONCALL_SCHEDULE]->(schedule)", cypher)
        self.assertIn("primary_oncall", cypher)
        self.assertIn("secondary_oncall", cypher)
        self.assertIn("owner_team", cypher)
        self.assertNotIn("service {id: 'service:playback'}", cypher)

    def test_formats_today_oncall_schedule_as_table(self):
        answer = hybrid_rag.format_oncall_schedule([
            {
                "service": "playback-service",
                "schedule": "Playback Primary On-call",
                "primary_oncall": "Emma Chen",
                "secondary_oncall": "Rahul Patel",
                "owner_team": "Platform Engineering",
            },
            {
                "service": "auth-service",
                "schedule": "No direct service on-call schedule modeled",
                "primary_oncall": "Escalate to owner team",
                "secondary_oncall": "Escalate to owner team",
                "owner_team": "identity-platform-team",
            },
        ])

        self.assertIn("| playback-service | Playback Primary On-call | Emma Chen | Rahul Patel | Platform Engineering |", answer)
        self.assertIn("| auth-service | No direct service on-call schedule modeled | Escalate to owner team | Escalate to owner team | identity-platform-team |", answer)
        self.assertIn("Direct service schedules: 1", answer)
        self.assertIn("Owner-team fallback rows: 1", answer)

    def test_oncall_graph_rag_returns_direct_schedule_answer(self):
        with patch.object(
            hybrid_rag,
            "graph",
            type("Graph", (), {
                "query": lambda self, cypher: [
                    {
                        "service": "playback-service",
                        "schedule": "Playback Primary On-call",
                        "primary_oncall": "Emma Chen",
                        "secondary_oncall": "Rahul Patel",
                        "owner_team": "Platform Engineering",
                    }
                ]
            })(),
        ):
            result = hybrid_rag.run_graph_rag("what is the oncall-schedule for today?")

        self.assertIn("| playback-service | Playback Primary On-call | Emma Chen | Rahul Patel | Platform Engineering |", result["answer"])

    def test_single_service_oncall_uses_direct_schedule_only(self):
        cypher = hybrid_rag.deterministic_cypher_for_query("who is oncall for ml-ranking-service")

        self.assertIsNotNone(cypher)
        self.assertIn("toLower(service.name) IN ['ml-ranking-service']", cypher)
        self.assertIn("HAS_ONCALL_SCHEDULE", cypher)
        self.assertIn("OWNED_BY_EXTERNAL_TEAM", cypher)
        self.assertNotIn("DEPENDS_ON", cypher)

    def test_multi_service_oncall_query_includes_all_requested_services(self):
        cypher = hybrid_rag.deterministic_cypher_for_query(
            "Who is oncall for ml-ranking-service and observability-service?"
        )

        self.assertIsNotNone(cypher)
        self.assertIn("'ml-ranking-service'", cypher)
        self.assertIn("'observability-service'", cypher)
        self.assertNotIn("LIMIT 1", cypher)
        self.assertNotIn("DEPENDS_ON", cypher)

    def test_formats_single_service_oncall_with_owner_fallback(self):
        answer = hybrid_rag.format_single_service_oncall([
            {
                "service": "ml-ranking-service",
                "schedule": "No direct service on-call schedule modeled",
                "primary_oncall": "Escalate to owner team",
                "secondary_oncall": "Escalate to owner team",
                "owner_team": "data-platform-team",
            }
        ])

        self.assertIn("| ml-ranking-service | No direct service on-call schedule modeled | Escalate to owner team | Escalate to owner team | data-platform-team |", answer)
        self.assertIn("Rows without a direct schedule", answer)
        self.assertIn("instead of inheriting", answer)

    def test_formats_multi_service_oncall_rows(self):
        answer = hybrid_rag.format_single_service_oncall([
            {
                "service": "ml-ranking-service",
                "schedule": "No direct service on-call schedule modeled",
                "primary_oncall": "Escalate to owner team",
                "secondary_oncall": "Escalate to owner team",
                "owner_team": "data-platform-team",
            },
            {
                "service": "observability-service",
                "schedule": "Observability Platform On-call",
                "primary_oncall": "Aisha Khan",
                "secondary_oncall": "Luca Romano",
                "owner_team": "Reliability Engineering",
            },
        ])

        self.assertIn("| ml-ranking-service | No direct service on-call schedule modeled", answer)
        self.assertIn("| observability-service | Observability Platform On-call | Aisha Khan | Luca Romano | Reliability Engineering |", answer)

    def test_run_graph_rag_returns_structured_payload(self):
        with patch.object(
            hybrid_rag,
            "graph_node",
            return_value={
                "context": ["Graph Analysis: answer"],
                "answer": "answer",
                "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "trace": {
                    "mode": "graph",
                    "stages": [hybrid_rag.make_trace_stage("Graph retrieval", "complete", "Returned 1 row")],
                    "evidence": {"vector": [], "graph": [{"row_count": 1}], "merged": []},
                    "known_gaps": ["gap"],
                },
            },
        ):
            result = hybrid_rag.run_graph_rag("who is oncall for ml-ranking-service")

        self.assertEqual(result["structured"]["query"], "who is oncall for ml-ranking-service")
        self.assertEqual(result["structured"]["route"], "graph")
        self.assertEqual(result["structured"]["answer"], "answer")
        self.assertEqual(result["structured"]["known_gaps"], ["gap"])

    def test_dashboard_query_includes_requested_services(self):
        cypher = hybrid_rag.deterministic_cypher_for_query(
            "Which dashboards cover ml-ranking-service and observability-service?"
        )

        self.assertIsNotNone(cypher)
        self.assertIn("'ml-ranking-service'", cypher)
        self.assertIn("'observability-service'", cypher)
        self.assertIn("HAS_DASHBOARD", cypher)

    def test_missing_dashboard_query_uses_anti_join(self):
        cypher = hybrid_rag.deterministic_cypher_for_query(
            "Which services are missing dashboard coverage in the catalog?"
        )

        self.assertIsNotNone(cypher)
        self.assertIn("WHERE NOT (service)-[:HAS_DASHBOARD]->(:Dashboard)", cypher)

    def test_formats_service_dashboards(self):
        answer = hybrid_rag.format_service_dashboards([
            {
                "service": "ml-ranking-service",
                "dashboard": "Recommendation Freshness Dashboard",
                "dashboard_description": "Grafana dashboard for recommendation freshness",
                "owner_team": "data-platform-team",
            },
            {
                "service": "observability-service",
                "dashboard": "Platform SLO Dashboard",
                "dashboard_description": "Grafana dashboard for service SLOs",
                "owner_team": "Reliability Engineering",
            },
        ])

        self.assertIn("| ml-ranking-service | Recommendation Freshness Dashboard", answer)
        self.assertIn("| observability-service | Platform SLO Dashboard", answer)

    def test_live_telemetry_query_is_not_answered_from_static_data(self):
        self.assertTrue(hybrid_rag.is_live_telemetry_query("What is the live CPU usage for playback-service right now?"))

        graph_result = hybrid_rag.run_graph_rag("What is the live CPU usage for playback-service right now?")
        vector_result = hybrid_rag.run_vector_rag("What is the live CPU usage for playback-service right now?")

        self.assertIn("cannot answer this from the current dataset", graph_result["answer"])
        self.assertIn("cannot answer this from the current dataset", vector_result["answer"])
        self.assertIn("live telemetry connector", graph_result["answer"])
        self.assertIn("live telemetry connector", vector_result["answer"])

    def test_billing_service_runbook_uses_service_template(self):
        cypher = hybrid_rag.deterministic_cypher_for_query("What does the billing service runbook cover?")

        self.assertIsNotNone(cypher)
        self.assertIn("service:billing", cypher)
        self.assertIn("HAS_RUNBOOK", cypher)
        self.assertIn("runbook_description", cypher)

    def test_formats_service_runbooks(self):
        answer = hybrid_rag.format_service_runbooks([
            {
                "service": "billing-service",
                "runbook": "Billing Incident Runbook",
                "runbook_description": "Steps for payment anomalies, double charges, and ledger reconciliation",
            }
        ])

        self.assertIn("billing-service runbooks:", answer)
        self.assertIn("Billing Incident Runbook", answer)
        self.assertIn("payment anomalies", answer)

    def test_formats_graph_paths_as_readable_relationships(self):
        formatted = hybrid_rag.format_graph_results([
            {
                "nodes": ["Emma Chen", "Playback Primary On-call", "playback-service"],
                "relationships": ["CURRENT_PRIMARY_ONCALL", "HAS_ONCALL_SCHEDULE"],
            }
        ])

        self.assertIn(
            "Emma Chen -[CURRENT_PRIMARY_ONCALL]- Playback Primary On-call -[HAS_ONCALL_SCHEDULE]- playback-service",
            formatted,
        )

    def test_router_vector_flow(self):
        # Descriptive query should favor vector
        query = "What is the nexusgraph-ai project?"
        inputs = {"query": query, "context": []}
        
        nodes_visited = []
        for output in app.stream(inputs):
            for key in output.keys():
                nodes_visited.append(key)
        
        self.assertIn("router", nodes_visited)
        self.assertIn("vector_node", nodes_visited)
        self.assertIn("synthesizer_node", nodes_visited)

    def test_router_graph_flow(self):
        # Relationship query should favor graph
        query = "How is Emma Chen related to the playback service?"
        inputs = {"query": query, "context": []}
        
        nodes_visited = []
        for output in app.stream(inputs):
            for key in output.keys():
                nodes_visited.append(key)
        
        self.assertIn("router", nodes_visited)
        self.assertIn("graph_node", nodes_visited)
        self.assertIn("synthesizer_node", nodes_visited)

if __name__ == "__main__":
    unittest.main()
