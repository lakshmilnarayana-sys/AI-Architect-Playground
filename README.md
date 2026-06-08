# AI Architect Playground

A hands-on playground for practising AI architecture patterns, building small end-to-end projects, and documenting what works in applied enterprise AI.

The goal of this repository is not to be one production application. It is a portfolio-style workspace for turning course learnings, certification requirements, and architecture ideas into runnable examples.

## Focus Areas

- Retrieval-Augmented Generation, or RAG
- GraphRAG and knowledge graphs
- AI agents and tool-using workflows
- Evaluation and comparison of AI systems
- Synthetic enterprise datasets
- Applied architecture patterns for organizational AI
- Demo apps, notebooks, and reproducible project scaffolds

## Repository Structure

```text
projects/
  nexusgraph-ai/
```

Each project should be self-contained and include its own data, source code, evaluation artifacts, documentation, and demo instructions.

## Projects

### nexusgraph-ai

GraphRAG for Organizational Knowledge and Decision Intelligence.

This project uses a synthetic streaming-company dataset to model people, teams, projects, services, skills, tools, documents, decisions, audits, and incidents as a knowledge graph. It compares GraphRAG against vector RAG on relationship-heavy organizational questions.

Location:

```text
projects/nexusgraph-ai
```

## Suggested Project Template

```text
README.md
data/
graph/
src/
app/
evaluation/
docs/
```

## How To Use This Repo

1. Pick one AI architecture concept to practise.
2. Create a focused project under `projects/`.
3. Use synthetic but realistic data.
4. Build the simplest runnable demo.
5. Add evaluation queries and comparison notes.
6. Document architecture tradeoffs and next steps.

## Deployment Preference

Projects should run locally first. For demos, prefer simple hosted options such as Streamlit Community Cloud or Hugging Face Spaces when they match the project stack.
