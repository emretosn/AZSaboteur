"""Ansible wrapper — playbook runner (stub for Phase 2)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from saboteur.utils.output import console, print_error, print_success

ANSIBLE_DIR = Path(__file__).resolve().parent.parent.parent / "ansible"


class AnsibleRunner:
    """Wraps Ansible playbook execution."""

    def __init__(self, working_dir: Path | None = None) -> None:
        self.working_dir = working_dir or ANSIBLE_DIR

    def run_playbook(
        self,
        playbook: str,
        inventory: str | None = None,
        extra_vars: dict | None = None,
    ) -> bool:
        playbook_path = self.working_dir / "playbooks" / playbook
        if not playbook_path.exists():
            print_error(f"Playbook not found: {playbook_path}")
            return False

        args = ["ansible-playbook", str(playbook_path)]
        if inventory:
            args.extend(["-i", inventory])
        if extra_vars:
            import json
            args.extend(["--extra-vars", json.dumps(extra_vars)])

        console.print(f"⠋ Running playbook: {playbook}...", style="info")
        result = subprocess.run(args, cwd=self.working_dir, text=True)
        if result.returncode == 0:
            print_success(f"Playbook {playbook} completed")
            return True
        print_error(f"Playbook {playbook} failed")
        return False
