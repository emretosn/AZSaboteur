"""Ansible wrapper — playbook runner for post-Terraform provisioning."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from saboteur.deploy.inventory import generate_inventory
from saboteur.utils.output import console, print_error, print_info, print_success

ANSIBLE_DIR = Path(__file__).resolve().parent.parent.parent / "ansible"


class AnsibleRunner:
    """Wraps Ansible playbook execution."""

    def __init__(
        self,
        working_dir: Path | None = None,
        verbose: bool = False,
    ) -> None:
        self.working_dir = working_dir or ANSIBLE_DIR
        self.verbose = verbose

    def provision_scenario(
        self,
        tf_outputs: dict[str, Any],
        chain_steps: list[dict[str, Any]],
        credentials: dict[str, str],
        flags: dict[str, str],
        kali_password: str,
    ) -> bool:
        """Generate inventory from Terraform outputs and run the site playbook.

        Returns True on success.
        """
        print_info("Generating Ansible inventory from Terraform outputs...")
        inventory_path = generate_inventory(
            tf_outputs=tf_outputs,
            chain_steps=chain_steps,
            credentials=credentials,
            flags=flags,
            kali_password=kali_password,
        )
        print_success(f"Inventory written to {inventory_path}")

        return self.run_playbook(
            playbook="site.yml",
            inventory=str(inventory_path),
        )

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

        if self.verbose:
            args.append("-vv")
            print_info(f"Running: {' '.join(args)}")
            result = subprocess.run(
                args,
                cwd=self.working_dir,
                stdout=sys.stdout,
                stderr=sys.stderr,
                text=True,
            )
        else:
            with console.status(
                "[bold blue]Provisioning vulnerable services...",
                spinner="dots",
                spinner_style="blue",
            ):
                result = subprocess.run(
                    args, cwd=self.working_dir, capture_output=True, text=True,
                )

        if result.returncode == 0:
            print_success(f"Playbook {playbook} completed")
            return True
        print_error(f"Playbook {playbook} failed")
        if not self.verbose and hasattr(result, "stderr") and result.stderr:
            print_error(result.stderr[-500:])
        return False
