# Design Spec: Enterprise Demo Ready NexusGraph

**Date:** 2026-06-10
**Topic:** Hardening NexusGraph into an enterprise-ready GraphRAG demo

## 1. Goal

Make NexusGraph a reliable enterprise demo for Streamflix, an imaginary streaming services company. The demo should clearly explain static synthetic data, show how raw operational knowledge becomes both a graph database and a vector database, and produce grounded answers that demonstrate the different strengths of Vector RAG, Graph RAG, and Hybrid RAG.

This is not a full production rebuild. It is a demo-platform hardening pass focused on answer quality, evidence, repeatability, and presentation.

## 2. Target Architecture

The current prototype works, but responsibilities are concentrated in `src/hybrid_rag.py` and the Streamlit app knows too much about runtime behavior. The enterprise demo version will use clearer boundaries:

- `src/ingestion/`: normalize CSV, YAML, markdown, and graph files into chunk records and graph records.
- `src/retrieval/`: separate vector retrieval, graph retrieval, hybrid orchestration, deterministic graph templates, and answer synthesis.
- `src/evidence.py`: define common evidence structures used by Vector, Graph, and Hybrid flows.
- `src/evaluation/`: run curated demo questions and validate expected evidence, answer shape, latency, and token usage.
- `app/streamlit_app.py`: remain the demo surface, but become a thinner UI layer for story, catalog, query workbench, evidence panels, and metrics.

## 3. RAG Contracts

The webpage will explain the retrieval modes using this same meaning:

### Vector RAG

Answers from semantic chunks only. Best for runbooks, incident notes, architecture docs, SLO descriptions, and "what guidance exists?" questions. It should show retrieved chunks and source files.

### Graph RAG

Answers from exact relationships only. Best for service ownership, on-call schedules, dependencies, dashboards, SLO links, and catalog completeness. It should show Cypher, row counts, and relationship paths or tables.

### Hybrid RAG

Starts with a service/topic resolver, then pulls both graph facts and vector text into one evidence bundle. It should not contradict Graph RAG. If vector evidence is weak but graph evidence is strong, Hybrid should say that. If graph has no relationship but vector has document guidance, Hybrid should say that too.

## 4. Answer Format

Every answer should be grounded and structured:

```text
Answer
Evidence used
Known gaps
Recommended next step
```

This keeps the demo honest. For example, "What is the on-call schedule for today across all services?" should return all services, direct primary and secondary engineers where modeled, and clearly mark static synthetic fallback rows as owner-team escalation only.

## 5. Data And Chunking Story

The app should continue to tell the Streamflix story:

- Streamflix is an imaginary streaming services company.
- The current data is static synthetic data.
- The project is using this phase to learn and validate retrieval patterns before moving to dynamic operational content.
- Raw data includes services, teams, incidents, runbooks, dashboards, SLOs, on-call schedules, escalation policies, documents, and decisions.
- Graph DB represents exact entities and relationships.
- Vector DB represents semantic chunks with source metadata.

The chunking strategy should be visible on the webpage:

- Graph nodes become self-contained chunks with id, type, name, and description.
- Graph relationships become sentence-like chunks describing source, relationship, and target.
- Source artifacts become document chunks with file/source metadata.
- Chunks keep enough metadata to trace answers back to graph ids or raw files.

## 6. Enterprise Demo UI

The Streamlit app should guide the audience through a clear operational story:

- Intro: Streamflix background, static synthetic data disclaimer, and problem statement.
- Raw data: what the dataset contains and how it maps into graph/vector stores.
- RAG mode explainer: Vector vs Graph vs Hybrid using the approved descriptions.
- Software catalog: services, owners, runbooks, dashboards, SLOs, dependencies, environments, and on-call coverage.
- Demo query workbench: curated questions focused on services, SLOs, incidents, runbooks, dependencies, and operational readiness.
- Results: side-by-side Vector, Graph, and Hybrid answers with latency, token use, evidence, and known gaps.
- Validation: a curated question set that can be run before the demo to prove expected behavior.

## 7. Behind The Scenes Search Trace

When the user runs a query, the app should show an interactive "Behind the scenes" area that combines two views:

- **Execution timeline:** compact stages for query intake, router, vector retrieval, graph retrieval, evidence merge, and synthesis. Each stage should show status, elapsed time where available, and the key output from that stage.
- **Evidence and answer split:** the answer remains visible beside or near the supporting evidence, so the audience can see why the answer was produced.

Each run should expose:

- router decision and reason
- vector retrieved chunks, source files, scores, and metadata
- graph Cypher, row count, and result rows or relationship paths
- merged evidence bundle
- known gaps, such as synthetic static data or missing live rotation feeds
- final answer, token usage, and latency

## 8. Validation

The hardened demo should include automated checks for:

- vector store can answer semantic runbook/document questions with source metadata
- graph store can answer service ownership, on-call, SLO, dashboard, and dependency questions
- hybrid answers include both graph and vector evidence when both exist
- hybrid answers do not contradict graph facts
- on-call schedule query returns all services and marks fallback rows
- software catalog has no unexplained gaps for critical demo fields
- token usage and latency are displayed for each RAG mode

## 9. Out Of Scope

This pass does not add:

- production authentication or RBAC
- multi-tenant isolation
- live Slack, Jira, PagerDuty, Datadog, or service-catalog connectors
- autonomous agent actions
- cloud deployment hardening

Those are future iterations after the enterprise demo is stable and defensible.

## 10. Success Criteria

- The app tells a coherent Streamflix incident-readiness story.
- Vector, Graph, and Hybrid modes are visibly and behaviorally distinct.
- Hybrid answers are evidence-driven and do not conflict with graph answers.
- The software catalog is complete enough for demo services.
- The vector and graph stores can be rebuilt repeatably.
- A demo validation suite passes before presenting.
- The query UI shows an execution timeline and evidence split so the audience can inspect what happened behind the scenes.
