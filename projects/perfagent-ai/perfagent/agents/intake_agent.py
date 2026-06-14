from __future__ import annotations

from pathlib import Path

from perfagent.core.state import EvaluationState, initial_state
from perfagent.core.workspace import Workspace


def intake(state: EvaluationState) -> EvaluationState:
    workspace = Workspace(Path(state["output_dir"]))
    workspace.create()
    workspace.write_state(state)
    return state


def create_state(**kwargs: object) -> EvaluationState:
    return initial_state(**kwargs)  # type: ignore[arg-type]

