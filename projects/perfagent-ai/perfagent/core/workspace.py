from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from perfagent.core.artifacts import write_json
from perfagent.core.state import EvaluationState


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def input_dir(self) -> Path:
        return self.root / "input"

    @property
    def generated_dir(self) -> Path:
        return self.root / "generated"

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.root / "processed"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    def create(self) -> None:
        for directory in [
            self.input_dir,
            self.generated_dir,
            self.raw_dir,
            self.processed_dir,
            self.reports_dir,
            self.state_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    def copy_openapi(self, source: Path) -> Path:
        destination = self.input_dir / source.name
        shutil.copyfile(source, destination)
        return destination

    def write_state(self, state: EvaluationState) -> None:
        write_json(self.state_dir / "evaluation_state.json", dict(state))

