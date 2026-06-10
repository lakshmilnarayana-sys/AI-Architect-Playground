# TODOS

Backlog items captured during the 2026-06-10 eng review of the
enterprise-demo-trace diff (see
`docs/superpowers/plans/2026-06-10-enterprise-demo-trace.md` for the full
GSTACK REVIEW REPORT).

## Infra / test collection

- **Fix `from config import ...` absolute imports.** `src/vector_query.py:12`,
  `src/vector_ingest.py:13`, and `src/vector_rag.py:11` use bare
  `from config import ...` / `from vector_query import ...`, which only
  resolves when `src/` itself is on `sys.path`. Running `pytest tests/` from
  the repo root fails to collect 4 test files (including the new
  `tests/test_vector_query.py`) with `ModuleNotFoundError: No module named
  'config'`. `PYTHONPATH=src pytest tests/` passes all 42. Fix: switch these
  to `from src.config import ...` / `from .config import ...` to match how
  `tests/test_hybrid_rag.py` already imports `src` as a package, so the suite
  collects without `PYTHONPATH=src`.

## Performance

- **Hybrid panel doubles backend retrieval calls.** Once the Hybrid panel is
  added (3-way comparison), `run_hybrid_rag` internally calls `vector_node`
  and `graph_node` again on top of the standalone vector/graph panels' calls
  — 2x retrieval cost per demo click (2x embedding searches, 2x
  Cypher-generation LLM calls for non-deterministic queries). Accepted for
  the first cut of the Hybrid panel for simplicity. Revisit if click latency
  becomes noticeably annoying:
  - Option B: restructure `_run` so vector_node/graph_node each run once and
    all three responses (vector/graph/hybrid) are derived from the shared
    results.
  - Option C: have the UI build the Hybrid trace via
    `merge_traces("hybrid", results["vector"]["trace"],
    results["graph"]["trace"])` directly, reusing the vector/graph panels'
    already-fetched results instead of calling `run_hybrid_rag`.

## Documentation

- **Plan Task 6 verification command is stale.**
  `docs/superpowers/plans/2026-06-10-enterprise-demo-trace.md` Task 6 Step 1
  references `tests.test_streamlit_trace_helpers`, which doesn't exist — it
  was implemented as `tests/test_ui_trace.py` instead (3/3 tests pass).
  Update the verification command to reference `tests.test_ui_trace`.

## Design system

- **Formalize DESIGN.md from the new CSS token set.** The 2026-06-10 design
  review of the enterprise-demo-trace diff (Pass 5, finding 4A) extracts a
  shared CSS custom-properties block (`--bg-panel`, `--bg-card`, `--border`,
  `--text-primary`, `--text-muted`, `--accent-indigo`, `--accent-emerald`,
  `--accent-amber`, `--accent-hybrid`) used across `.ng-wrap`, `.store-grid`,
  and `.ev-flow`. No `DESIGN.md` exists yet to document these tokens, naming
  conventions, or how to add future accent colors. Once 4A lands, run
  `/design-consultation` to author `DESIGN.md` from this token set.

## Architecture

- **LangGraph `StateGraph` workflow is dead in the production path.**
  `src/hybrid_rag.py:1013-1058` (`workflow` / `app = workflow.compile()`)
  reimplements the same vector/graph/compare routing that `_run()`
  (`src/hybrid_rag.py:1060-1144`) does manually — `_run` is what all 3
  `run_*_rag` entrypoints actually use. `app` is only exercised by
  `__main__` and 2 tests (`test_router_vector_flow`,
  `test_router_graph_flow`, ~29s combined runtime). Either document why both
  implementations exist (e.g., "`app` is the LangGraph-idiomatic reference
  implementation, `_run` is the fast path") or remove the unused compiled
  graph and its 2 slow tests to avoid the routing logic drifting between two
  places.
