from __future__ import annotations

import builtins
import sys
import types
from pathlib import Path

import pytest

from perfagent import workflow_graph


EXPECTED_STAGE_NODES = [
    "initialize_workspace",
    "analyze_contract",
    "plan_strategy",
    "generate_tests",
    "execute_load",
    "collect_signals",
    "analyze_results",
    "render_report",
]


class FakeCompiledGraph:
    def __init__(self, graph):
        self.graph = graph

    def invoke(self, state):
        current = self.graph.entry_point
        while current != self.graph.end:
            state = self.graph.nodes[current](state)
            current = self.graph.edges[current]
        return state


class FakeStateGraph:
    instances = []

    def __init__(self, state_type):
        self.state_type = state_type
        self.nodes = {}
        self.edges = {}
        self.entry_point = None
        self.end = None
        FakeStateGraph.instances.append(self)

    def add_node(self, name, func):
        self.nodes[name] = func

    def set_entry_point(self, name):
        self.entry_point = name

    def add_edge(self, start, end):
        self.edges[start] = end
        if end == "END":
            self.end = end

    def compile(self):
        return FakeCompiledGraph(self)


@pytest.fixture
def fake_langgraph(monkeypatch):
    FakeStateGraph.instances.clear()
    langgraph = types.ModuleType("langgraph")
    graph_module = types.ModuleType("langgraph.graph")
    graph_module.END = "END"
    graph_module.StateGraph = FakeStateGraph
    monkeypatch.setitem(sys.modules, "langgraph", langgraph)
    monkeypatch.setitem(sys.modules, "langgraph.graph", graph_module)
    return FakeStateGraph


def test_langgraph_workflow_builds_multiple_named_stage_nodes(fake_langgraph, monkeypatch, tmp_path):
    calls = []

    for node_name in EXPECTED_STAGE_NODES:
        stage_func_name = f"_stage_{node_name}"

        def stage(state, node_name=node_name):
            calls.append(node_name)
            if node_name == "render_report":
                state["result"] = {"release_decision": "PASS"}
            return state

        monkeypatch.setattr(workflow_graph, stage_func_name, stage)

    result = workflow_graph.run_langgraph_evaluation(
        service_name="payments-api",
        openapi_path=Path("examples/sample-openapi.yaml"),
        target_url="http://localhost:8080",
        runtime="go",
        slo_p95_ms=500,
        slo_error_rate_percent=1,
        duration="1m",
        output_dir=tmp_path,
        skip_run=True,
    )

    graph = fake_langgraph.instances[0]
    assert list(graph.nodes) == EXPECTED_STAGE_NODES
    assert graph.entry_point == "initialize_workspace"
    assert graph.edges["initialize_workspace"] == "analyze_contract"
    assert graph.edges["render_report"] == "END"
    assert calls == EXPECTED_STAGE_NODES
    assert result["release_decision"] == "PASS"


def test_langgraph_workflow_reports_missing_optional_dependency(monkeypatch, tmp_path):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "langgraph.graph":
            raise ImportError("langgraph not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="requires perfagent-ai\\[graph\\]"):
        workflow_graph.run_langgraph_evaluation(
            service_name="payments-api",
            openapi_path=Path("examples/sample-openapi.yaml"),
            target_url="http://localhost:8080",
            runtime="go",
            slo_p95_ms=500,
            slo_error_rate_percent=1,
            duration="1m",
            output_dir=tmp_path,
            skip_run=True,
        )
