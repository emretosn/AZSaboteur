"""Flag validation for submitted flags."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationResult:
    correct: bool
    step: int | None = None
    message: str = ""


class FlagValidator:
    """Validates player-submitted flags against the scenario's flag registry."""

    def __init__(self, flags: dict[int, str]) -> None:
        self.flags = flags
        self.solved: set[int] = set()

    def validate(self, submitted: str) -> ValidationResult:
        submitted = submitted.strip()
        for step, flag in self.flags.items():
            if submitted == flag:
                self.solved.add(step)
                total = len(self.flags)
                if len(self.solved) == total:
                    return ValidationResult(
                        correct=True,
                        step=step,
                        message=f"✓ Correct! Final flag — all {total} steps completed!",
                    )
                return ValidationResult(
                    correct=True,
                    step=step,
                    message=f"✓ Correct! Step {step + 1}/{total} completed.",
                )
        return ValidationResult(correct=False, message="✗ Incorrect flag. Keep trying!")

    @property
    def progress(self) -> str:
        return f"{len(self.solved)}/{len(self.flags)} steps completed"

    @property
    def is_complete(self) -> bool:
        return len(self.solved) == len(self.flags)
