"""Terraform wrapper — init, plan, apply, destroy."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from saboteur.utils.output import console, print_error, print_success

TERRAFORM_DIR = Path(__file__).resolve().parent.parent.parent / "terraform"


class TerraformRunner:
    """Wraps Terraform CLI commands for scenario deployment."""

    def __init__(self, working_dir: Path | None = None) -> None:
        self.working_dir = working_dir or TERRAFORM_DIR

    def _run(self, args: list[str], capture: bool = False) -> subprocess.CompletedProcess:
        cmd = ["terraform", *args]
        return subprocess.run(
            cmd,
            cwd=self.working_dir,
            capture_output=capture,
            text=True,
        )

    def init(self) -> bool:
        console.print("⠋ Initializing Terraform...", style="info")
        result = self._run(["init", "-input=false"], capture=True)
        if result.returncode == 0:
            print_success("Terraform initialized")
            return True
        print_error(f"Terraform init failed:\n{result.stderr}")
        return False

    def plan(self, var_file: Path | None = None) -> bool:
        args = ["plan", "-input=false"]
        if var_file:
            args.append(f"-var-file={var_file}")
        console.print("⠋ Planning infrastructure...", style="info")
        result = self._run(args)
        return result.returncode == 0

    def apply(self, var_file: Path | None = None, auto_approve: bool = True) -> bool:
        args = ["apply", "-input=false"]
        if auto_approve:
            args.append("-auto-approve")
        if var_file:
            args.append(f"-var-file={var_file}")
        console.print("⠋ Deploying infrastructure...", style="info")
        result = self._run(args)
        if result.returncode == 0:
            print_success("Infrastructure deployed")
            return True
        print_error("Terraform apply failed")
        return False

    def destroy(self, var_file: Path | None = None, auto_approve: bool = True) -> bool:
        args = ["destroy", "-input=false"]
        if auto_approve:
            args.append("-auto-approve")
        if var_file:
            args.append(f"-var-file={var_file}")
        console.print("⠋ Tearing down infrastructure...", style="info")
        result = self._run(args)
        if result.returncode == 0:
            print_success("All resources destroyed")
            return True
        print_error("Terraform destroy failed")
        return False

    def output(self) -> dict[str, Any]:
        result = self._run(["output", "-json"], capture=True)
        if result.returncode == 0:
            return json.loads(result.stdout)
        return {}

    def write_var_file(self, scenario_vars: dict[str, Any], filename: str = "scenario.auto.tfvars.json") -> Path:
        """Write scenario variables to a tfvars JSON file."""
        var_file = self.working_dir / filename
        with open(var_file, "w") as f:
            json.dump(scenario_vars, f, indent=2)
        return var_file
