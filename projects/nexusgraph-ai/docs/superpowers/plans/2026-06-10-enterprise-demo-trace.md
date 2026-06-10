# Enterprise Demo Trace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an enterprise-demo-ready behind-the-scenes search trace that explains Vector RAG, Graph RAG, and Hybrid RAG behavior with evidence, timeline stages, latency, and token usage.

**Architecture:** Keep the existing Streamlit and LangGraph prototype intact, but introduce a stable result contract around `hybrid_rag.py`. Each RAG runner returns `answer`, `route`, `token_usage`, and a `trace` dictionary containing timeline stages and evidence details. The Streamlit app renders approved Vector/Graph/Hybrid descriptions plus an expandable execution timeline and evidence/answer split. The visual treatment uses the approved B + C direction: an incident command center visual at the top of the page and evidence-flow graphics in each result trace.

**Tech Stack:** Python, Streamlit, LangChain/LangGraph, ChromaDB, Neo4j, unittest.

---

## File Structure

- Modify `src/hybrid_rag.py`: add trace helpers, attach vector evidence, graph evidence, deterministic Cypher, row counts, merged evidence, and synthesis stages to runner results.
- Modify `app/streamlit_app.py`: add RAG mode explainer copy, animated incident command center, evidence-flow cards, and timeline/evidence panels under the side-by-side answers.
- Create `src/ui_trace.py`: pure helper functions for trace formatting and evidence counts.
- Modify `tests/test_hybrid_rag.py`: assert all runners return trace data and that hybrid trace contains both vector and graph evidence.
- Create `tests/test_ui_trace.py`: test pure UI helper formatting functions without launching Streamlit.

## Task 1: Add Trace Contract Helpers

**Files:**
- Modify: `src/hybrid_rag.py`
- Test: `tests/test_hybrid_rag.py`

- [ ] **Step 1: Write failing tests for trace helper shape**

Add these tests to `tests/test_hybrid_rag.py`:

```python
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
        self.assertEqual(trace["known_gaps"], [])
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_hybrid_rag.HybridRagTests.test_make_trace_stage_shape tests.test_hybrid_rag.HybridRagTests.test_empty_trace_shape
```

Expected: failure because `make_trace_stage` and `empty_trace` do not exist.

- [ ] **Step 3: Implement trace helpers**

Add near `EMPTY_TOKEN_USAGE` in `src/hybrid_rag.py`:

```python
def make_trace_stage(
    name: str,
    status: str,
    summary: str,
    elapsed: float | None = None,
    details: Optional[dict] = None,
) -> dict:
    return {
        "name": name,
        "status": status,
        "summary": summary,
        "elapsed": elapsed,
        "details": details or {},
    }


def empty_trace(mode: str) -> dict:
    return {
        "mode": mode,
        "stages": [],
        "evidence": {
            "vector": [],
            "graph": [],
            "merged": [],
        },
        "known_gaps": [],
    }
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
python3 -m unittest tests.test_hybrid_rag.HybridRagTests.test_make_trace_stage_shape tests.test_hybrid_rag.HybridRagTests.test_empty_trace_shape
```

Expected: both tests pass.

## Task 2: Add Vector And Graph Evidence To Retrieval Nodes

**Files:**
- Modify: `src/hybrid_rag.py`
- Test: `tests/test_hybrid_rag.py`

- [ ] **Step 1: Write failing tests for node trace evidence**

Add these tests:

```python
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
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_hybrid_rag.HybridRagTests.test_vector_node_returns_trace_evidence tests.test_hybrid_rag.HybridRagTests.test_graph_node_returns_trace_evidence_for_deterministic_query
```

Expected: failure because retrieval nodes do not return `trace`.

- [ ] **Step 3: Update `vector_node`**

Replace `vector_node` in `src/hybrid_rag.py` with:

```python
def vector_node(state: State) -> dict:
    """Query the vector store and return semantic evidence."""
    results = query_vector_store(state["query"])
    matches = results["matches"]
    context = [f"Vector Store: {m['document']}" for m in matches]
    evidence = [
        {
            "source": match.get("metadata", {}).get("source", "unknown"),
            "kind": match.get("metadata", {}).get("kind", "unknown"),
            "distance": match.get("distance"),
            "metadata": match.get("metadata", {}),
            "text": match.get("document", ""),
        }
        for match in matches
    ]
    trace = empty_trace("vector")
    trace["stages"].append(make_trace_stage(
        "Vector retrieval",
        "complete",
        f"Retrieved {len(matches)} semantic chunks from ChromaDB.",
        details={"match_count": len(matches)},
    ))
    trace["evidence"]["vector"] = evidence
    return {"context": context, "trace": trace}
```

- [ ] **Step 4: Update `graph_node` trace returns**

Inside `graph_node`, after `results = graph.query(cypher)`, build graph evidence:

```python
        graph_evidence = {
            "cypher": cypher,
            "row_count": len(results),
            "rows": results,
            "deterministic": used_deterministic_cypher,
        }
        trace = empty_trace("graph")
        trace["stages"].append(make_trace_stage(
            "Graph retrieval",
            "complete",
            f"Returned {len(results)} rows from Neo4j.",
            details={"row_count": len(results), "deterministic": used_deterministic_cypher},
        ))
        trace["evidence"]["graph"] = [graph_evidence]
```

Then include `"trace": trace` in each successful return from `graph_node`. For rejected or exception returns, return a trace with a failed `Graph retrieval` stage and a known gap message.

- [ ] **Step 5: Run tests and verify pass**

Run:

```bash
python3 -m unittest tests.test_hybrid_rag.HybridRagTests.test_vector_node_returns_trace_evidence tests.test_hybrid_rag.HybridRagTests.test_graph_node_returns_trace_evidence_for_deterministic_query
```

Expected: both tests pass.

## Task 3: Merge Trace Data In Runner Functions

**Files:**
- Modify: `src/hybrid_rag.py`
- Test: `tests/test_hybrid_rag.py`

- [ ] **Step 1: Write failing tests for runner trace outputs**

Add:

```python
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
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_hybrid_rag.HybridRagTests.test_run_vector_rag_returns_trace tests.test_hybrid_rag.HybridRagTests.test_run_hybrid_rag_returns_merged_trace
```

Expected: failure because runner outputs do not include merged trace.

- [ ] **Step 3: Add trace merge helper**

Add to `src/hybrid_rag.py`:

```python
def merge_traces(mode: str, *traces: Optional[dict]) -> dict:
    merged = empty_trace(mode)
    for trace in traces:
        if not trace:
            continue
        merged["stages"].extend(trace.get("stages", []))
        evidence = trace.get("evidence", {})
        merged["evidence"]["vector"].extend(evidence.get("vector", []))
        merged["evidence"]["graph"].extend(evidence.get("graph", []))
        merged["evidence"]["merged"].extend(evidence.get("merged", []))
        merged["known_gaps"].extend(trace.get("known_gaps", []))
    if mode == "hybrid":
        merged["evidence"]["merged"].append({
            "summary": (
                f"Combined {len(merged['evidence']['vector'])} vector evidence items "
                f"and {len(merged['evidence']['graph'])} graph evidence items."
            )
        })
    return merged
```

- [ ] **Step 4: Update runner functions**

In `run_vector_rag`, `run_graph_rag`, and `run_hybrid_rag`, preserve the trace returned by node calls and append a `Synthesis` stage after `synthesizer_node` returns. Each result dictionary should include:

```python
{
    "answer": synthesized["answer"],
    "route": "vector",
    "token_usage": synthesized.get("token_usage", EMPTY_TOKEN_USAGE),
    "trace": trace,
}
```

Use `"graph"` and `"hybrid"` route values for the other runners.

- [ ] **Step 5: Run tests and verify pass**

Run:

```bash
python3 -m unittest tests.test_hybrid_rag.HybridRagTests.test_run_vector_rag_returns_trace tests.test_hybrid_rag.HybridRagTests.test_run_hybrid_rag_returns_merged_trace
```

Expected: both tests pass.

## Task 4: Add Streamlit RAG Explainer And Trace Rendering Helpers

**Files:**
- Modify: `app/streamlit_app.py`
- Create: `tests/test_streamlit_trace_helpers.py`

- [ ] **Step 1: Extract pure trace formatting helpers**

Add these helpers near `format_token_usage` in `app/streamlit_app.py`:

```python
def format_stage_elapsed(stage: dict) -> str:
    elapsed = stage.get("elapsed")
    if elapsed is None:
        return "not timed"
    return f"{float(elapsed):.2f}s"


def evidence_counts(trace: dict | None) -> dict:
    evidence = (trace or {}).get("evidence", {})
    return {
        "vector": len(evidence.get("vector", [])),
        "graph": len(evidence.get("graph", [])),
        "merged": len(evidence.get("merged", [])),
    }
```

- [ ] **Step 2: Write tests for helpers**

Create `tests/test_streamlit_trace_helpers.py`:

```python
import unittest

from app.streamlit_app import evidence_counts, format_stage_elapsed


class StreamlitTraceHelperTests(unittest.TestCase):
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
```

- [ ] **Step 3: Run helper tests**

Run:

```bash
python3 -m unittest tests.test_streamlit_trace_helpers
```

Expected: pass after helpers are added.

- [ ] **Step 4: Add webpage RAG mode explainer**

In `app/streamlit_app.py`, after the vector database metrics and before `Graph Shape`, add:

```python
st.subheader('How The RAG Modes Differ')
rag_cols = st.columns(3)
with rag_cols[0]:
    st.markdown(
        """
        **Vector RAG**

        Answers from semantic chunks only. Best for runbooks, incident notes,
        architecture docs, SLO descriptions, and "what guidance exists?" questions.
        It shows retrieved chunks and source files.
        """
    )
with rag_cols[1]:
    st.markdown(
        """
        **Graph RAG**

        Answers from exact relationships only. Best for service ownership,
        on-call schedules, dependencies, dashboards, SLO links, and catalog completeness.
        It shows Cypher, row counts, and relationship paths or tables.
        """
    )
with rag_cols[2]:
    st.markdown(
        """
        **Hybrid RAG**

        Starts with a service/topic resolver, then pulls both graph facts and vector
        text into one evidence bundle. It should not contradict Graph RAG. If one
        source is weak, Hybrid should say that clearly.
        """
    )
```

## Task 5: Render Behind-The-Scenes Timeline And Evidence Split

**Files:**
- Modify: `app/streamlit_app.py`

- [ ] **Step 1: Add trace rendering functions**

Add near the helper functions:

```python
def render_trace_timeline(trace: dict | None) -> None:
    trace = trace or {}
    stages = trace.get("stages", [])
    if not stages:
        st.info("No execution trace was returned for this run.")
        return

    timeline_cols = st.columns(len(stages))
    for col, stage in zip(timeline_cols, stages):
        col.metric(stage.get("name", "Stage"), format_stage_elapsed(stage))
        col.caption(stage.get("summary", "No summary available."))


def render_trace_evidence(trace: dict | None) -> None:
    trace = trace or {}
    counts = evidence_counts(trace)
    st.caption(
        f"Evidence: {counts['vector']} vector chunks · "
        f"{counts['graph']} graph result sets · {counts['merged']} merged notes"
    )

    evidence = trace.get("evidence", {})
    tab_vector, tab_graph, tab_merged, tab_gaps = st.tabs(["Vector", "Graph", "Merged", "Known gaps"])
    with tab_vector:
        vector_items = evidence.get("vector", [])
        if vector_items:
            st.dataframe(pd.DataFrame(vector_items), width="stretch")
        else:
            st.info("No vector evidence used.")
    with tab_graph:
        graph_items = evidence.get("graph", [])
        if graph_items:
            for item in graph_items:
                st.code(item.get("cypher", "No Cypher captured."), language="cypher")
                st.write(f"Rows returned: {item.get('row_count', 0)}")
                rows = item.get("rows", [])
                if rows:
                    st.dataframe(pd.DataFrame(rows), width="stretch")
        else:
            st.info("No graph evidence used.")
    with tab_merged:
        merged_items = evidence.get("merged", [])
        if merged_items:
            st.json(merged_items)
        else:
            st.info("No merged evidence notes.")
    with tab_gaps:
        gaps = trace.get("known_gaps", [])
        if gaps:
            for gap in gaps:
                st.warning(gap)
        else:
            st.success("No known gaps recorded for this run.")
```

- [ ] **Step 2: Add trace panels under each answer**

Inside the existing `for key, col in col_map.items():` loop, after the answer and caption:

```python
            with col.expander("Behind the scenes", expanded=False):
                render_trace_timeline(res.get("trace"))
                render_trace_evidence(res.get("trace"))
```

- [ ] **Step 3: Run syntax check**

Run:

```bash
python3 -m py_compile app/streamlit_app.py
```

Expected: no output and exit code 0.

## Task 6: Full Verification

**Files:**
- Modify only if tests reveal a defect: `src/hybrid_rag.py`, `app/streamlit_app.py`, tests touched above.

- [ ] **Step 1: Run focused unit tests**

Run:

```bash
python3 -m unittest tests.test_hybrid_rag tests.test_streamlit_trace_helpers tests.test_software_catalog tests.test_vector_query tests.test_vector_rag
```

Expected: all tests pass.

- [ ] **Step 2: Restart the app container**

Run:

```bash
docker compose restart app
```

Expected: `nexusgraph-ai-app` restarts successfully.

- [ ] **Step 3: Check Streamlit logs**

Run:

```bash
docker logs --tail 80 nexusgraph-ai-app
```

Expected: Streamlit app starts without import or runtime errors.

- [ ] **Step 4: Manual demo validation**

Open `http://localhost:8501` and run:

```text
What is the on-call schedule for today across all services?
```

Expected:

- Vector RAG returns semantic source evidence or states static data limitations.
- Graph RAG returns a table of all services with direct schedules or owner-team fallback.
- Hybrid RAG includes graph evidence and vector evidence where available.
- Each result has a collapsed `Behind the scenes` expander with timeline and evidence tabs.

- [ ] **Step 5: Commit implementation**

Commit only files changed by this implementation slice:

```bash
git add src/hybrid_rag.py app/streamlit_app.py tests/test_hybrid_rag.py tests/test_streamlit_trace_helpers.py docs/superpowers/plans/2026-06-10-enterprise-demo-trace.md
git commit -m "Add enterprise demo search trace"
```

If commit signing prompts for a passphrase in this environment, use:

```bash
git -c commit.gpgsign=false -c tag.gpgsign=false commit -m "Add enterprise demo search trace"
```

## GSTACK REVIEW REPORT

Reviewed the uncommitted working-tree diff (Tasks 1-5 implemented, Task 6
not yet run) against this plan as spec, plus the out-of-plan additions
(Software Catalog explorer, Incident Command Center, Project Story).

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | ISSUES OPEN | 6 issues, 1 critical gap |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | CLEAN | 6 issues, 0 unresolved |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

Suite status: **42/42 passed** (`PYTHONPATH=src pytest tests/ -v`, 33.9s).
Staleness: review performed against working tree on top of HEAD `65ea0e5`
(no commits made during review) — not stale.

### Decisions

- **D2 — Restore Hybrid RAG as a 3rd comparison panel.** The plan's 3-way
  Vector/Graph/Hybrid comparison was narrowed to a 2-way Vector/Graph
  comparison in the implementation: `run_hybrid_rag` and the
  `merge_traces` "hybrid" branch (producing `evidence["merged"]`) are
  fully built and unit-tested (`test_run_hybrid_rag_returns_merged_trace`,
  `test_hybrid_rag_synthesizes_vector_and_graph_context`), but
  `app/streamlit_app.py` only ever calls `run_graph_rag`/`run_vector_rag`,
  and `render_rag_mode_explainer` + the "How to read this comparison"
  popover describe only Graph (primary) and Vector (baseline) — Hybrid is
  absent from the product's own narrative. **Decision: restore it as a 3rd
  panel** (→ T2, T3).
- **D3 — Hybrid trace-honesty fix.** In `_run()` (`src/hybrid_rag.py:1091-1120`),
  compare-mode always runs both `vector_node` and `graph_node`, but for
  oncall/dashboard/runbook/live-telemetry queries the deterministic graph
  answer short-circuits — the final answer never uses vector context, yet
  `merge_traces("hybrid", ...)` still reports a combined vector+graph
  evidence summary. **Decision: append a `known_gaps` note** when this
  shortcut fires in hybrid mode (→ T4).
- **D4 — Evidence summary cards always show duplicate counts.**
  `render_trace_evidence` (`app/streamlit_app.py:399-403`) shows two cards
  per mode that are structurally guaranteed to be identical (Vector
  Chunks == Source Files; Graph Query == Relationship Evidence), since
  `evidence_counts()` only exposes one number per source. **Decision:
  compute real distinct second metrics** from existing evidence metadata
  (→ T5).
- **D5 — New Software Catalog pure functions are untested.**
  `catalog_domain`, `has_catalog_value`, `readiness_items`,
  `readiness_score` (`app/streamlit_app.py:453-483`) drive the headline
  readiness % and OK/Gap badges and have zero coverage despite being
  trivially testable. **Decision: add `tests/test_catalog_helpers.py`**
  following the `test_software_catalog.py` precedent (→ T6).
- **D6 — Hybrid panel will double retrieval calls (forward-looking from D2).**
  `run_hybrid_rag` internally re-runs `vector_node`+`graph_node` on top of
  the standalone vector/graph panels' calls — 2x embedding searches and 2x
  Cypher-generation LLM calls per demo click once D2 ships. **Decision:
  accept for now**, tracked in `TODOS.md` with the two refactor options
  considered (shared retrieval in `_run`, or UI-side `merge_traces`).
- **D7 — TODOS.md additions** (all 4 selected): the pre-existing
  `from config import ...` absolute-import issue (breaks `pytest tests/`
  without `PYTHONPATH=src`), D6's retrieval-duplication note, this plan's
  stale Task 6 verification command (`tests.test_streamlit_trace_helpers`
  → `tests.test_ui_trace`), and the dead-in-production-path LangGraph
  `StateGraph`/`app.compile()`.
- **D8 — Outside Voice: skipped** (recommended) — all open items were
  resolved with concrete file:line evidence; no unresolved architectural
  ambiguity remained.

### Critical gap (REGRESSION RULE — flagged directly)

**[CRITICAL] (confidence: 8/10) `src/hybrid_rag.py:905-921` and
`:967-978`** — `graph_node`'s "rejected unsafe/empty Cypher" branch and its
exception/error branch both build trace-contract data added by this diff
(`empty_trace`, `make_trace_stage(..., "rejected"/"error", ...)`,
`known_gaps.append(...)`) with **zero test coverage**. The error branch is
the most realistic live-demo failure (a Neo4j blip mid-presentation) —
exactly the moment a bug in untested error-trace code would compound the
outage. → **T1 (P1)**.

### Diagrams

**Trace contract data flow — current state:**
```
+-----------------------------------------------------------+
|  Streamlit UI - "Ask NexusGraph" expander                  |
|  ThreadPoolExecutor(max_workers=2)                         |
+--------------------+-----------------------+---------------+
                      |                       |
                      v                       v
              run_graph_rag()          run_vector_rag()
              route="graph"            route="vector"
                      |                       |
                      v                       v
                graph_node()            vector_node()
                      |                       |
           trace.evidence.graph     trace.evidence.vector
                      |                       |
                      v                       v
            render_trace_timeline / render_trace_evidence
            tabs: [Evidence | Known gaps]   (per panel)

   run_hybrid_rag() / route="compare"  -->  never called from UI
   merge_traces("hybrid", ...)
     -> evidence.merged              -->  never rendered (no "Merged" tab)
```

**Trace contract data flow — target state after T2/T3/T4:**
```
+----------------------------------------------------------------------+
|  Streamlit UI - "Ask NexusGraph" expander                             |
|  ThreadPoolExecutor(max_workers=3)                                    |
+---------+-------------------+----------------------+------------------+
          v                   v                      v
   run_graph_rag()      run_vector_rag()       run_hybrid_rag()
   route="graph"        route="vector"         route="compare"
          |                   |                      |
          v                   v          vector_node()+graph_node()
    graph_node()        vector_node()                |
          |                   |          merge_traces("hybrid",...)
          |                   |          evidence: vector/graph/merged
          |                   |          + known_gaps note (T4) when
          |                   |            deterministic shortcut fires
          v                   v                      v
   [Evidence |          [Evidence |         [Evidence | Merged (T3) |
    Known gaps]          Known gaps]          Known gaps]   <- 3rd column
   "GraphRAG (primary)" "Vector (baseline)"  "Hybrid"
```

**graph_node coverage map (T1 critical gap):**
```
graph_node(state)
 +- live-telemetry-unavailable ........ tested (***)
 +- deterministic success ............. tested (***)
 +- non-deterministic LLM-Cypher ...... low-confidence, indirect only (*)
 +- rejected/empty Cypher (905-921) ... UNTESTED  <-- T1 CRITICAL
 \- exception/error (967-978) ......... UNTESTED  <-- T1 CRITICAL
```

### Failure modes

1. **Neo4j connection drops mid-demo** → `graph_node`'s exception branch
   (`967-978`) sets `trace["stages"]` status `"error"` with
   `details={"error","cypher"}` and a `known_gaps` note, returns no
   `"answer"` → `_run` falls through to the full synthesis path
   (`1121-1144`), calling the LLM to "synthesize" from
   `context=["Graph Analysis: Error querying graph. Check logs for
   details."]`. No test verifies this produces a sensible answer or that
   the trace shape is correct. **No test + new trace-construction code +
   most-likely-live failure = critical (T1).**
2. **Generated Cypher rejected as unsafe/empty** → `graph_node`'s
   `905-921` branch returns `context=["Graph Analysis: Generated query was
   rejected as unsafe or empty."]` with no `"answer"`, same
   fall-through-to-synthesis pattern, same zero coverage. **(T1).**
3. **ThreadPoolExecutor per-panel exception** (`app/streamlit_app.py`,
   `timed()` wrapper) — already handled gracefully: the except branch
   returns a dict without a `"structured"`/`"trace"` key, and
   `render_trace_timeline`/`render_trace_evidence` both do
   `trace = trace or {}` and show `"No execution trace was returned for
   this run."` when `stages` is empty. **No action needed** — listed here
   for completeness since it's the kind of silent gap this section looks
   for, but it is in fact handled.

### NOT in scope

- The narrative/demo-script content of `render_incident_command_center()`
  and `render_project_story()` (the "Streamflix" fictional scenario
  framing) — reviewed only for structure (expanders, embedded image,
  no broken calls), not for content/copy quality.
- `render_software_catalog_explorer` and other `render_*` UI functions —
  covered only via the `[→E2E]` manual-verification note in the test plan;
  no Streamlit `AppTest` harness is proposed for a personal demo app.
- Pre-existing Cypher-hardening block (`clean_cypher`, `is_read_only`,
  `WRITE_KEYWORDS`, `rewrite_property_filters`, etc.) — predates this
  diff. The one new deterministic template added by this diff (security +
  platform-engineering projects query) was spot-checked: read-only
  `MATCH`/`RETURN`, no injection surface.
- `graph/edges.csv` and `evaluation/comparison_results.md` data edits —
  checked for consistency with the new deterministic Cypher template and
  `test_catalog_has_dashboard_for_every_service`/Environment column, found
  consistent; not audited row-by-row.
- `requirements.txt`'s new `pyvis==0.3.2` dependency — not
  security/license-audited beyond noting it as a new dependency.

### What already exists (confirmed working / good)

- Trace contract helpers `make_trace_stage`/`empty_trace`/`merge_traces`
  (Task 1) — match the plan exactly, 100% tested.
- `vector_node`/`graph_node` trace-evidence attachment (Task 2) and trace
  merging in `_run`/`run_*_rag` (Task 3) — implemented and match plan
  intent, aside from the T1 gap above.
- `render_trace_timeline` — **improves on the plan**: caps at
  `min(len(stages), 5)` columns with modulo wrap instead of the plan's
  `st.columns(len(stages))`, which would misbehave for >5 or 0 stages.
- `get_vector_store` (`lru_cache` + `threading.Lock`) — solid concurrency
  fix for the new `ThreadPoolExecutor`-based parallel graph+vector calls,
  well-tested (`test_concurrent_queries_share_one_embedding_model`).
- `software_catalog.build_software_catalog` — well-tested against real
  `graph/nodes.csv`/`graph/edges.csv` (4/4), the internal/external Owner
  merge logic is correct.
- `src/ui_trace.py` (`format_stage_elapsed`, `evidence_counts`) — small,
  clean, fully tested (3/3).
- Pre-existing, lower-priority observations not added to TODOS.md by user
  choice: `print()`-based debug statements remain in `graph_node`
  (`L897, 902, 907, 923, 978`) — predate this diff.

### Worktree parallelization strategy

Implementation Tasks T1-T6 split into 3 lanes by file overlap:

| Task | Files | Depends on | Lane |
|---|---|---|---|
| T1 | tests/test_hybrid_rag.py | - | A |
| T4 | src/hybrid_rag.py, tests/test_hybrid_rag.py | - | A |
| T2 | app/streamlit_app.py | - | B |
| T3 | app/streamlit_app.py | T2 | B |
| T5 | app/streamlit_app.py, src/ui_trace.py, tests/test_ui_trace.py | T3 | B |
| T6 | tests/test_catalog_helpers.py (new) | - | C |

- **Lane A** (T1 -> T4, sequential): both touch `tests/test_hybrid_rag.py`
  -- do back-to-back in one worktree to avoid a merge conflict.
- **Lane B** (T2 -> T3 -> T5, sequential): all three touch
  `app/streamlit_app.py`'s comparison-panel / `render_trace_evidence`
  area -- must be sequential.
- **Lane C** (T6, independent): new file only, no overlap with A or B.

Lanes A, B, and C touch disjoint file sets and can run in **3 parallel
worktrees**. Total wall time ~= Lane B (~5hrs human / ~90min CC), the
longest lane.

### Implementation Tasks

- [ ] T1 (P1, CRITICAL, human:~30min / CC:~10min) Test graph_node rejected-cypher and error branches (`tests/test_hybrid_rag.py`)
- [ ] T2 (P1, human:~3hrs / CC:~45min) Restore Hybrid RAG as 3rd comparison panel (`app/streamlit_app.py`)
- [ ] T3 (P1, human:~1hr / CC:~20min) Add Merged evidence tab to render_trace_evidence — depends on T2
- [ ] T4 (P1, human:~30min / CC:~15min) Add known_gaps note for hybrid deterministic-shortcut trace honesty (`src/hybrid_rag.py`, `tests/test_hybrid_rag.py`)
- [ ] T5 (P2, human:~1hr / CC:~25min) Compute distinct second metric for evidence summary cards — depends on T3
- [ ] T6 (P2, human:~20min / CC:~15min) Add `tests/test_catalog_helpers.py` for catalog pure functions

JSONL: `~/.gstack/projects/lakshmilnarayana-sys-AI-Architect-Playground/tasks-eng-review-20260610-155443.jsonl`
Test plan: `~/.gstack/projects/lakshmilnarayana-sys-AI-Architect-Playground/lnv-main-eng-review-test-plan-20260610-155443.md`
TODOS: `TODOS.md` (4 entries from D7)

---

## Design Review (plan-design-review)

Reviewed the same uncommitted diff plus this plan as spec. Scope (D1):
full review across all 7 passes (`review-sections.md`), code-based
evidence only — no AI mockups generated, no OpenAI spend. Visual evidence
for the Pass 6 finding: rendered HTML comparison of `.ev-flow` at
660px/430px/320px container widths
(`~/.gstack/projects/lakshmilnarayana-sys-AI-Architect-Playground/designs/ev-flow-narrow-check-20260610/ev-flow-width-check.html`).

### Pass scores (before -> after)

| Pass | Before | After | Resolution |
|---|---|---|---|
| 1. Information Architecture | 3/10 | 8/10 | 1A -> T7 |
| 2. Interaction State Coverage | 5/10 | 9/10 | 2A -> T8 |
| 3. User Journey & Emotional Arc | 3/10 | 8/10 | merged into 1A -> T7 |
| 4. AI Slop Risk + Hard Rules | 6/10 | 9/10 | 3B -> T9 |
| 5. Design System Alignment | 3/10 | 7/10 | 4A -> T10 (+ TODOS: `/design-consultation`) |
| 6. Responsive & Accessibility | 4/10 | 8/10 | 5A -> T11 |
| 7. Unresolved Design Decisions | 1 open | 0 open | 6A -> T12 |

**Overall: 4.0/10 -> 8.2/10.** 6 findings, 0 unresolved.

### Decisions

- **1A — Merge fragmented project-story expanders + Incident Command
  Center into one "About This Demo" section, move first.**
  `render_project_story` is split across 5 sibling expanders with
  inconsistent numbering ("Overview: Why This Demo Exists", "1. The
  problem...", "2. What raw data...", "Example: one rich graph data
  source", "3. Next iteration..."), positioned after the action expanders
  ("Ask NexusGraph", "GraphRAG Demo Queries"). The most visceral content in
  the diff, `render_incident_command_center`, is buried inside this group
  — a 30-second visitor never sees it. **Decision: merge into one expander
  with a single narrative, move to the top of the page** (-> T7).

  ```
  BEFORE (current order):
    Title + caption
    +-- "Ask NexusGraph" (expanded)        <- query input + GraphRAG/Vector results
    +-- "GraphRAG Demo Queries" (expanded) <- 3 demo query cards
    +-- "Overview: Why This Demo Exists" (collapsed)        --+
    +-- "1. The problem..." (collapsed)                       |  fragmented
    +-- "2. What raw data..." (collapsed)                     |  story group
    +-- "Example: one rich graph data source" (collapsed)     |  (5 expanders,
    +-- "3. Next iteration..." (collapsed)                  --+   inconsistent
    +-- Incident Command Center (collapsed, within/near above group)
    +-- Software Catalog explorer (collapsed)
    +-- Tech Stack (collapsed)
    +-- Store Overview: Neo4j/ChromaDB/Demo Query Set (collapsed)
    +-- Graph Visualization (collapsed)

  AFTER (T7):
    Title + caption
    +-- "About This Demo" (NEW, single expander, FIRST)
    |     - Incident Command Center visual (animated, moved up)
    |     - One flowing narrative (was 5 fragmented sections)
    +-- "Ask NexusGraph" (expanded)
    +-- "GraphRAG Demo Queries" (expanded)
    +-- Software Catalog explorer (collapsed, unchanged position)
    +-- Tech Stack (collapsed, unchanged position)
    +-- Store Overview (collapsed, unchanged position)
    +-- Graph Visualization (collapsed, unchanged position)
  ```

- **2A — Dedicated `st.error()` for failed comparison panels.** When a
  panel's backend raises, `{"answer": f"Error: {e}", ...}` renders raw
  exception text in the same markdown slot as a successful answer — no
  `st.error`, no icon, no distinct styling. This is exactly the moment
  T1's Neo4j-blip scenario would surface to a live audience. **Decision:
  switch to `{"answer": None, "error": str(e), ...}` and render
  `st.error(...)` for failed panels** instead of the markdown answer block
  (-> T8). Extends naturally to T2's 3rd panel.

- **3B — Drop unloaded "Inter" font reference (AI Slop blacklist #11).**
  `.ng-wrap`/`.store-grid`/`.ev-flow` declare
  `Inter, ui-sans-serif, system-ui, -apple-system` but Inter is never
  loaded (no `@import`/`<link>`, no `.streamlit/config.toml`); these 3
  blocks render via `components.html` iframes, which don't inherit
  page-level fonts either — so all 3 silently fall back to `system-ui`,
  while native Streamlit widgets use Streamlit's own default typeface.
  **Decision: drop "Inter", use the same typeface Streamlit's native
  widgets already render in** — zero new network requests, unifies custom
  HTML with native chrome (-> T9).

- **4A — Extract shared CSS custom-properties (design tokens).** No
  `DESIGN.md` exists; `.ng-wrap`/`.store-grid`/`.ev-flow` each redeclare
  the same indigo/emerald/amber identity-color + navy/slate
  background/border/text palette inline. T2 needs a 4th "Hybrid" identity
  color soon. **Decision: extract `--bg-panel`, `--bg-card`, `--border`,
  `--text-primary`, `--text-muted`, `--accent-indigo`, `--accent-emerald`,
  `--accent-amber`, and reserve `--accent-hybrid`** (-> T10). Follow-up
  `/design-consultation` to author `DESIGN.md` from these tokens added to
  `TODOS.md`.

- **5A — `.ev-flow` responsive breakpoint + `.ng-value` font size.**
  Unlike `.ng-grid`/`.ng-metrics` (`@media max-width:780px`) and
  `.store-grid` (`@media max-width:860px`), `.ev-flow`
  (`render_trace_evidence`, the newest grid) has no breakpoint. The
  rendered HTML comparison (660px today vs. ~430px after T2's 3-panel
  layout vs. 320px) shows card text wrapping/clipping inside the fixed
  `height=125` iframe once T2 ships. Separately, `.ng-value` (Incident
  Command Center metric values — actual content, not captions) is 15px,
  under the 16px body-text hard rule. **Decision: add
  `@media (max-width: 480px) {.ev-flow{grid-template-columns:1fr}}` (stack
  to 1 column) + adjust the iframe height for the stacked layout; bump
  `.ng-value` to 16px** (-> T11). Directly unblocks T2's 3-panel layout.

- **6A — Hybrid-mode `.ev-flow` summary cards.**
  `render_trace_evidence`'s card-label logic is a binary
  `mode == "vector"` / `else` (graph-style). Once T2 adds
  `mode == "hybrid"`, it falls into the graph branch by default — a hybrid
  trace has non-zero `counts["vector"]` too (merge_traces concatenates
  both), but it would be entirely invisible in the always-visible summary
  row, reachable only via T3's "Merged" tab. **Decision: add a
  `mode == "hybrid"` branch — card1 = "Vector Chunks"/`counts["vector"]`,
  card2 = "Graph Query"/`counts["graph"]`, card3 = "Known Gaps"
  (unchanged)** (-> T12, implement alongside T2/T3). Refines T2/T3, not a
  new task.

### NOT in scope (design review)

- AI-generated mockups (`$D variants`/`compare`) — declined per D1, no
  OpenAI spend.
- Full WCAG contrast audit (color-by-color) — only the `.ng-value` 15px
  font-size hard-rule hit was raised.
- Authoring `DESIGN.md` itself — 4A creates the token values; formalizing
  them into a documented system is a `/design-consultation` follow-up
  (added to `TODOS.md`).
- `.streamlit/config.toml` theme overhaul — 3B resolves the font issue by
  removing the unloaded "Inter" reference, not by adding new theme config.
- T1 (eng review's critical untested error-branch gap) — only its UI-side
  counterpart (2A/T8) is addressed here.
- Pre-existing `TODOS.md` items (absolute-import fix, hybrid-retrieval
  perf, stale Plan Task 6 command, dead LangGraph `StateGraph`) — not
  revisited.

### What already exists (design review)

- `.ng-grid`/`.ng-metrics` (`@media max-width:780px`) and `.store-grid`
  (`@media max-width:860px`) already establish the responsive-breakpoint
  pattern that 5A extends to `.ev-flow`.
- Loading/empty/success states already solid: `st.spinner`,
  `st.warning("Please enter a query first.")`,
  `st.info("No execution trace was returned for this run.")`,
  `st.info`/`st.success` in evidence tabs. Only the error state (2A) was
  missing dedicated treatment.
- The indigo/emerald/amber identity-color palette is already used
  consistently across `.store-card`/`.ev-card` — 4A formalizes it into
  tokens, doesn't invent a new palette.
- Streamlit's native default typeface already gives native widgets a
  deliberate, real typeface — 3B extends that same choice to the 3 custom
  HTML blocks instead of adding a new font dependency.
- `evidence_counts(trace)` (`src/ui_trace.py`) already computes both
  `counts["vector"]` and `counts["graph"]` — 6A is a labeling/branching
  change on data already available, no new plumbing.
- `trace = trace or {}` already makes `render_trace_timeline`/
  `render_trace_evidence` safe with `trace=None` — 2A's failed-panel path
  relies on this unchanged.

### Implementation Tasks (design review)

- [ ] T7 (P2, human:~1hr / CC:~30min) Merge project-story expanders +
  Incident Command Center into one "About This Demo" section, move first
  (`app/streamlit_app.py`)
- [ ] T8 (P1, human:~30min / CC:~15min) Dedicated `st.error()` for failed
  comparison panels (`app/streamlit_app.py`)
- [ ] T9 (P3, human:~10min / CC:~5min) Drop unloaded "Inter" font
  reference, match Streamlit's native typeface (`app/streamlit_app.py`)
- [ ] T10 (P2, human:~1hr / CC:~35min) Extract shared CSS custom-properties
  design tokens (`app/streamlit_app.py`)
- [ ] T11 (P1, human:~30min / CC:~15min) Add `.ev-flow` responsive
  breakpoint + fix `.ng-value` font size — depends on landing before/with
  T2 (`app/streamlit_app.py`)
- [ ] T12 (P1, human:~30min / CC:~15min) Add hybrid-mode branch to
  `render_trace_evidence` summary cards — depends on T2, T3
  (`app/streamlit_app.py`)

JSONL: `~/.gstack/projects/lakshmilnarayana-sys-AI-Architect-Playground/tasks-design-review-20260610-172454.jsonl`
TODOS: `TODOS.md` (1 new entry: formalize `DESIGN.md` from 4A's tokens via `/design-consultation`)

---

**VERDICT:** ENG REVIEW NOT CLEARED — gate remains open until T1 lands
(CRITICAL: untested `graph_node` rejected/error trace branches,
`src/hybrid_rag.py:905-921` and `:967-978`). All other eng findings
resolved into accepted decisions (D2-D6) or backlog items (D7); T1 added
to Implementation Tasks (P1). Outside Voice offered and skipped by user
choice (D8).

DESIGN REVIEW CLEAN — all 7 passes evaluated (overall 4.0/10 -> 8.2/10), 6
findings (1A-6A) all resolved into Implementation Tasks T7-T12, 0
unresolved decisions. T11 (`.ev-flow` responsive fix) directly unblocks
T2's 3-panel layout and T12 (hybrid summary-card labels) refines T2/T3 —
recommend sequencing T9-T12 alongside T2/T3 in Lane B.

**Combined plan status: ISSUES OPEN** (T1 gate). Implementation Tasks
T1-T12 are fully specified and ready to execute; T1 must land before the
gate clears.

NO UNRESOLVED DECISIONS
