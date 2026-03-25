"""Interactive prompts for CLI configuration using InquirerPy."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from InquirerPy import inquirer  # pyright: ignore[reportPrivateImportUsage]
from InquirerPy.separator import Separator  # pyright: ignore[reportPrivateImportUsage]

from saboteur.modules.base import ModuleCategory
from saboteur.utils.output import print_info, print_warning


def _find_custom_images() -> list[dict[str, str]]:
    """Query Azure for AZSaboteur custom images."""
    try:
        result = subprocess.run(
            [
                "az", "image", "list",
                "--query", "[?tags.project=='azsaboteur'].{id:id, name:name, location:location}",
                "-o", "json",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return []


def prompt_deploy_config() -> dict[str, Any]:
    """Walk the user through deploy configuration interactively."""
    config: dict[str, Any] = {}

    # --- Chain length ---
    config["chain_length"] = inquirer.number(
        message="Number of attack chain steps:",
        default=3,
        min_allowed=0,
        max_allowed=10,
    ).execute()
    config["chain_length"] = int(config["chain_length"])

    # --- Categories ---
    if config["chain_length"] > 0:
        all_cats = [c.value for c in ModuleCategory]
        selected = inquirer.checkbox(
            message="Filter by categories (space to select, enter to confirm, skip for all):",
            choices=all_cats,
        ).execute()
        config["categories"] = [ModuleCategory(c) for c in selected] if selected else None
    else:
        config["categories"] = None

    # --- Region ---
    config["region"] = inquirer.select(
        message="Azure region:",
        choices=[
            "westeurope",
            "eastus",
            "eastus2",
            "northeurope",
            "uksouth",
            "centralus",
            "westus2",
            "southeastasia",
        ],
        default="westeurope",
    ).execute()

    # --- Custom image ---
    images = _find_custom_images()
    if images:
        image_choices: list[Any] = [{"name": "None (use marketplace image + cloud-init)", "value": ""}]
        image_choices.append(Separator())
        for img in images:
            image_choices.append({"name": f"{img['name']} ({img['location']})", "value": img["id"]})
        config["image"] = inquirer.select(
            message="Kali box image:",
            choices=image_choices,
            default="",
        ).execute()
    else:
        config["image"] = ""

    # --- Seed ---
    use_seed = inquirer.confirm(
        message="Set a random seed for reproducibility?",
        default=False,
    ).execute()
    if use_seed:
        config["seed"] = int(
            inquirer.number(message="Seed value:", default=42).execute()
        )
    else:
        config["seed"] = None

    # --- Verbose ---
    config["verbose"] = inquirer.confirm(
        message="Enable verbose Terraform output?",
        default=False,
    ).execute()

    return config


def prompt_generate_config() -> dict[str, Any]:
    """Walk the user through generate (dry-run) configuration interactively."""
    config: dict[str, Any] = {}

    # --- Chain length ---
    config["chain_length"] = inquirer.number(
        message="Number of attack chain steps (0 = infra only):",
        default=3,
        min_allowed=0,
        max_allowed=10,
    ).execute()
    config["chain_length"] = int(config["chain_length"])

    # --- Categories ---
    if config["chain_length"] > 0:
        all_cats = [c.value for c in ModuleCategory]
        selected = inquirer.checkbox(
            message="Filter by categories (space to select, enter to confirm, skip for all):",
            choices=all_cats,
        ).execute()
        config["categories"] = [ModuleCategory(c) for c in selected] if selected else None
    else:
        config["categories"] = None

    # --- Region ---
    config["region"] = inquirer.select(
        message="Azure region:",
        choices=[
            "westeurope",
            "eastus",
            "eastus2",
            "northeurope",
            "uksouth",
            "centralus",
            "westus2",
            "southeastasia",
        ],
        default="westeurope",
    ).execute()

    # --- Seed ---
    use_seed = inquirer.confirm(
        message="Set a random seed for reproducibility?",
        default=False,
    ).execute()
    if use_seed:
        config["seed"] = int(
            inquirer.number(message="Seed value:", default=42).execute()
        )
    else:
        config["seed"] = None

    # --- Verbose ---
    config["verbose"] = inquirer.confirm(
        message="Show full chain details?",
        default=False,
    ).execute()

    # --- Output file ---
    save = inquirer.confirm(
        message="Save scenario to a JSON file?",
        default=False,
    ).execute()
    if save:
        config["output_file"] = inquirer.text(
            message="Output file path:",
            default="scenario.json",
        ).execute()
    else:
        config["output_file"] = None

    return config


def prompt_destroy_instance() -> dict[str, Any]:
    """Let the user pick a deployment to destroy."""
    from saboteur.config import StateManager

    config: dict[str, Any] = {}
    state = StateManager()
    deployments = state.all

    if not deployments:
        return {"instance": None}

    choices = []
    for dep in deployments:
        chain_str = " → ".join(dep.chain) if dep.chain else "infra-only"
        label = f"{dep.scenario_id}  [{dep.status}]  {chain_str}  ({dep.region})"
        choices.append({"name": label, "value": dep.scenario_id})

    config["instance"] = inquirer.select(
        message="Select deployment to destroy:",
        choices=choices,
    ).execute()

    config["verbose"] = inquirer.confirm(
        message="Enable verbose Terraform output?",
        default=False,
    ).execute()

    return config
