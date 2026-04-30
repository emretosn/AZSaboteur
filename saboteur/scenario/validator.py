"""Flag validation for submitted flags."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from saboteur.config import STATE_DIR

VALIDATION_DIR = STATE_DIR / "validation"


@dataclass
class ValidationResult:
    correct: bool
    step: int | None = None
    already_solved: bool = False
    solved_count: int = 0
    total: int = 0
    message: str = ""


class FlagValidator:
    """Validates player-submitted flags against the scenario's flag registry."""

    def __init__(self, flags: dict[int, str], scenario_id: str | None = None) -> None:
        self.flags = flags
        self.solved: set[int] = set()
        self._state_file: Path | None = None
        if scenario_id:
            self._state_file = VALIDATION_DIR / f"{scenario_id}.json"
            self._load()

    def _load(self) -> None:
        if self._state_file and self._state_file.exists():
            with open(self._state_file) as f:
                data = json.load(f)
            saved_flags = data.get("flags", {})
            for step in data.get("solved", []):
                # Only restore if the step exists and the flag hasn't changed
                if step in self.flags and saved_flags.get(str(step)) == self.flags[step]:
                    self.solved.add(step)

    def _save(self) -> None:
        if self._state_file:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "solved": sorted(self.solved),
                "flags": {str(k): v for k, v in self.flags.items()},
            }
            with open(self._state_file, "w") as f:
                json.dump(data, f)

    @staticmethod
    def clear_state(scenario_id: str) -> None:
        """Remove persisted validation state for a scenario."""
        state_file = VALIDATION_DIR / f"{scenario_id}.json"
        state_file.unlink(missing_ok=True)

    @staticmethod
    def clear_all_state() -> None:
        """Remove all persisted validation state."""
        if VALIDATION_DIR.exists():
            for f in VALIDATION_DIR.glob("*.json"):
                f.unlink(missing_ok=True)

    def validate(self, submitted: str) -> ValidationResult:
        submitted = submitted.strip()
        total = len(self.flags)
        for step, flag in self.flags.items():
            if submitted == flag:
                if step in self.solved:
                    return ValidationResult(
                        correct=True,
                        step=step,
                        already_solved=True,
                        solved_count=len(self.solved),
                        total=total,
                        message=f"Step {step + 1} was already solved.",
                    )
                self.solved.add(step)
                self._save()
                solved_count = len(self.solved)
                if solved_count == total:
                    return ValidationResult(
                        correct=True,
                        step=step,
                        solved_count=solved_count,
                        total=total,
                        message=f"Correct! Step {step + 1} solved. All {total} flags captured!",
                    )
                return ValidationResult(
                    correct=True,
                    step=step,
                    solved_count=solved_count,
                    total=total,
                    message=f"Correct! Step {step + 1} solved. Progress: {solved_count}/{total}",
                )
        return ValidationResult(
            correct=False,
            solved_count=len(self.solved),
            total=total,
            message="Incorrect flag. Keep trying!",
        )

    @property
    def progress(self) -> str:
        return f"{len(self.solved)}/{len(self.flags)} flags captured"

    @property
    def is_complete(self) -> bool:
        return len(self.solved) == len(self.flags)
