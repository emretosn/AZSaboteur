"""Configuration management and deployment state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STATE_DIR = Path.home() / ".azsaboteur"
STATE_FILE = STATE_DIR / "state.json"


@dataclass
class DeploymentState:
    """Tracks a single active deployment."""

    scenario_id: str
    region: str
    chain: list[str]
    flags: dict[int, str]
    status: str = "deployed"
    terraform_dir: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "region": self.region,
            "chain": self.chain,
            "flags": {str(k): v for k, v in self.flags.items()},
            "status": self.status,
            "terraform_dir": self.terraform_dir,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeploymentState:
        flags = {int(k): v for k, v in data.get("flags", {}).items()}
        return cls(
            scenario_id=data["scenario_id"],
            region=data["region"],
            chain=data["chain"],
            flags=flags,
            status=data.get("status", "deployed"),
            terraform_dir=data.get("terraform_dir", ""),
            created_at=data.get("created_at", ""),
        )


class StateManager:
    """Manages persistent state for active deployments."""

    def __init__(self, state_file: Path = STATE_FILE) -> None:
        self._state_file = state_file
        self._deployments: dict[str, DeploymentState] = {}
        self._load()

    def _load(self) -> None:
        if self._state_file.exists():
            with open(self._state_file) as f:
                data = json.load(f)
            for sid, dep_data in data.get("deployments", {}).items():
                self._deployments[sid] = DeploymentState.from_dict(dep_data)

    def _save(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"deployments": {k: v.to_dict() for k, v in self._deployments.items()}}
        with open(self._state_file, "w") as f:
            json.dump(data, f, indent=2)

    def add(self, deployment: DeploymentState) -> None:
        self._deployments[deployment.scenario_id] = deployment
        self._save()

    def remove(self, scenario_id: str) -> None:
        self._deployments.pop(scenario_id, None)
        self._save()

    def get(self, scenario_id: str) -> DeploymentState | None:
        return self._deployments.get(scenario_id)

    @property
    def active(self) -> list[DeploymentState]:
        return [d for d in self._deployments.values() if d.status == "deployed"]

    @property
    def all(self) -> list[DeploymentState]:
        return list(self._deployments.values())
