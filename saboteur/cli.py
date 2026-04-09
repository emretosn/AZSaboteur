"""CLI commands for AZSaboteur."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from saboteur.config import DeploymentState, StateManager
from saboteur.deploy.ansible import AnsibleRunner
from saboteur.deploy.terraform import TerraformRunner
from saboteur.modules.base import ModuleCategory
from saboteur.modules.catalog import load_catalog
from saboteur.scenario.engine import ScenarioConfig, ScenarioEngine
from saboteur.scenario.validator import FlagValidator
from saboteur.utils.azure_auth import accept_kali_terms, get_subscription_id
from saboteur.utils.vm_health import wait_for_rdp
from saboteur.utils.output import (
    console as out,
    print_banner,
    print_chain_summary,
    print_chain_table,
    print_chain_verbose,
    print_error,
    print_info,
    print_mission_briefing,
    print_success,
    print_warning,
)

app = typer.Typer(
    name="saboteur",
    help="AZSaboteur — Dynamic Azure Cloud Attack Lab Generator",
    no_args_is_help=True,
    invoke_without_command=True,
)

MODULES_DIR = Path(__file__).resolve().parent.parent / "modules"


def _load_engine(seed: int | None = None) -> ScenarioEngine:
    catalog = load_catalog(MODULES_DIR)
    if len(catalog) == 0:
        print_error("No vulnerability modules found. Add YAML definitions to modules/")
        raise typer.Exit(1)
    return ScenarioEngine(catalog, seed=seed)


def _has_explicit_flags(ctx: typer.Context) -> bool:
    """Return True if the user passed any explicit CLI flags (not just defaults)."""
    # Click tracks where each parameter value came from
    source = getattr(ctx, "_parameter_source", {}) or {}
    for key, origin in source.items():
        # ParameterSource.COMMANDLINE == 1; anything from the command line means scripted mode
        if hasattr(origin, "name") and origin.name == "COMMANDLINE":
            return True
    return False


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------

@app.command()
def generate(
    ctx: typer.Context,
    chain_length: int = typer.Option(3, "--chain-length", "-n", min=0, help="Number of steps in the attack chain (0 = infra only)"),
    categories: Optional[str] = typer.Option(None, "--categories", "-c", help="Comma-separated categories: web,identity,compute,storage,networking"),
    region: str = typer.Option("westeurope", "--region", "-r", help="Azure region"),
    seed: Optional[int] = typer.Option(None, "--seed", "-s", help="Random seed for reproducibility"),
    output_file: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path (JSON)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full chain details"),
) -> None:
    """Generate a scenario without deploying (dry run)."""
    print_banner()

    if not _has_explicit_flags(ctx):
        from saboteur.utils.prompts import prompt_generate_config
        cfg = prompt_generate_config()
        chain_length = cfg["chain_length"]
        cat_list = cfg["categories"]
        region = cfg["region"]
        seed = cfg["seed"]
        output_file = cfg["output_file"]
        verbose = cfg["verbose"]
    else:
        cat_list = _parse_categories(categories)

    config = ScenarioConfig(
        chain_length=chain_length,
        categories=cat_list,
        region=region,
        seed=seed,
    )

    engine = _load_engine(seed)
    scenario = engine.generate(config)

    chain_data = [scenario.graph.get_module(mid).to_dict() for mid in scenario.graph.topo_order()]
    if chain_data:
        if verbose:
            print_chain_verbose(chain_data)
        else:
            print_chain_summary(chain_data)
    else:
        print_info("Infra-only mode — no attack chain generated")
    print_info(f"Scenario ID: {scenario.scenario_id}")

    if output_file:
        data = scenario.to_terraform_vars()
        data["graph"] = scenario.graph.to_dict()
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)
        print_success(f"Scenario written to {output_file}")


# ---------------------------------------------------------------------------
# deploy
# ---------------------------------------------------------------------------

@app.command()
def deploy(
    ctx: typer.Context,
    chain_length: int = typer.Option(3, "--chain-length", "-n", min=0, help="Number of steps in the attack chain (0 = infra only)"),
    categories: Optional[str] = typer.Option(None, "--categories", "-c", help="Comma-separated categories"),
    region: str = typer.Option("westeurope", "--region", "-r", help="Azure region"),
    seed: Optional[int] = typer.Option(None, "--seed", "-s", help="Random seed"),
    subscription_id: Optional[str] = typer.Option(None, "--subscription", help="Azure subscription ID (auto-detected from az cli if omitted)"),
    image: Optional[str] = typer.Option(None, "--image", help="Custom Kali image resource ID (from 'packer build'). Skips cloud-init."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Stream Terraform output for debugging"),
) -> None:
    """Generate and deploy a scenario to Azure."""
    print_banner()

    if not _has_explicit_flags(ctx):
        from saboteur.utils.prompts import prompt_deploy_config
        cfg = prompt_deploy_config()
        chain_length = cfg["chain_length"]
        cat_list = cfg["categories"]
        region = cfg["region"]
        seed = cfg["seed"]
        image = cfg["image"] or None
        verbose = cfg["verbose"]
    else:
        cat_list = _parse_categories(categories)

    sub_id = subscription_id or get_subscription_id()
    if not sub_id:
        print_error("No Azure subscription found. Run 'az login' or pass --subscription.")
        raise typer.Exit(1)

    config = ScenarioConfig(
        chain_length=chain_length,
        categories=cat_list,
        region=region,
        subscription_id=sub_id,
        seed=seed,
    )

    engine = _load_engine(seed)
    scenario = engine.generate(config)

    chain_data = [scenario.graph.get_module(mid).to_dict() for mid in scenario.graph.topo_order()]
    if chain_data:
        if verbose:
            print_chain_verbose(chain_data)
        else:
            print_chain_summary(chain_data)
    else:
        print_info("Infra-only mode — deploying Kali box and networking only")
    print_info(f"Scenario ID: {scenario.scenario_id}")

    if not image:
        if not accept_kali_terms():
            print_error("Failed to accept Kali Linux marketplace terms. Check your Azure permissions.")
            raise typer.Exit(1)

    tf = TerraformRunner(verbose=verbose, scenario_id=scenario.scenario_id)
    tf_vars = scenario.to_terraform_vars()
    if image:
        tf_vars["kali_custom_image_id"] = image
    var_file = tf.write_var_file(tf_vars)
    tf.generate_chain_tf(tf_vars["chain"])

    if not tf.init():
        raise typer.Exit(1)

    # Record state *before* apply so a failed deploy can still be destroyed.
    state = StateManager()
    deployment = DeploymentState(
        scenario_id=scenario.scenario_id,
        region=region,
        chain=[scenario.graph.get_module(mid).id for mid in scenario.graph.topo_order()],
        flags=scenario.flags,
        status="deploying",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    state.add(deployment)

    if not tf.apply(var_file=var_file):
        deployment.status = "failed"
        state.add(deployment)
        print_warning(
            f"Deployment {scenario.scenario_id} failed. "
            f"Run 'saboteur destroy {scenario.scenario_id}' to clean up."
        )
        raise typer.Exit(1)

    tf_outputs = tf.output()
    kali_ip = tf_outputs.get("kali_public_ip", {}).get("value", "<pending>")

    # --- Phase 2: Ansible provisioning ---
    if chain_data:
        chain_steps = []
        for i, node_id in enumerate(scenario.graph.topo_order()):
            module = scenario.graph.get_module(node_id)
            chain_steps.append({
                "step": i,
                "module_id": module.id,
                "ansible_role": module.ansible_role,
            })

        kali_pass = scenario.kali_credentials["password"]
        ansible = AnsibleRunner(verbose=verbose)
        if not ansible.provision_scenario(
            tf_outputs=tf_outputs,
            chain_steps=chain_steps,
            credentials=scenario.credentials,
            flags={str(k): v for k, v in scenario.flags.items()},
            kali_password=kali_pass,
        ):
            deployment.status = "deployed"
            state.add(deployment)
            print_warning(
                "Ansible provisioning failed — infrastructure is deployed but "
                "vulnerable services may not be running. You can re-run Ansible manually."
            )
        else:
            deployment.status = "deployed"
            state.add(deployment)
    else:
        deployment.status = "deployed"
        state.add(deployment)

    if not image:
        rg_name = f"rg-{scenario.scenario_id}"
        vm_name = f"vm-kali-{scenario.scenario_id}"
        wait_for_rdp(rg_name, vm_name)

    kali_user = scenario.kali_credentials["username"]
    kali_pass = scenario.kali_credentials["password"]
    print_success("Deployment complete!")
    conn_cmd = f"xfreerdp /v:{kali_ip} /u:{kali_user} /p:'{kali_pass}' /cert:ignore"
    if chain_data:
        print_mission_briefing(
            target=f"{kali_ip} (Kali box)",
            objective="Scan the network from the Kali box, exploit the chain, and find the flags.",
            connection_info=conn_cmd,
        )
    else:
        print_mission_briefing(
            target=f"{kali_ip} (Kali box)",
            objective="Infra-only deployment — no attack chain. Use this environment for testing.",
            connection_info=conn_cmd,
        )


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------

@app.command()
def destroy(
    ctx: typer.Context,
    instance: Optional[str] = typer.Argument(None, help="Scenario ID to destroy"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Stream Terraform output for debugging"),
) -> None:
    """Tear down a deployed scenario."""
    state = StateManager()

    if instance is None and not _has_explicit_flags(ctx):
        if not state.all:
            print_info("No deployments to destroy")
            return
        from saboteur.utils.prompts import prompt_destroy_instance
        cfg = prompt_destroy_instance()
        instance = cfg["instance"]
        verbose = cfg["verbose"]
        if not instance:
            print_info("No deployments to destroy")
            return

    if not instance:
        print_error("No scenario ID provided. Usage: saboteur destroy <SCENARIO_ID>")
        raise typer.Exit(1)

    deployment = state.get(instance)
    if not deployment:
        print_error(f"No deployment found with ID: {instance}")
        raise typer.Exit(1)

    if deployment.status == "failed":
        print_warning(f"Deployment {instance} was in a failed state — cleaning up.")

    tf = TerraformRunner(verbose=verbose, scenario_id=instance)
    if not tf.init():
        raise typer.Exit(1)

    if tf.destroy():
        state.remove(instance)
        print_success(f"Deployment {instance} destroyed")
    else:
        print_error(
            "Destroy failed — resources may be stuck in state due to permission errors.\n"
            "Run 'saboteur clean' to reset local state, then delete orphaned resources in the Azure portal."
        )
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# clean
# ---------------------------------------------------------------------------

@app.command()
def clean() -> None:
    """Reset local Terraform state and saboteur tracking when destroy fails.

    Use this when 'saboteur destroy' can't delete resources (e.g. permission errors).
    It removes all resources from Terraform state and clears saboteur deployment tracking.
    Orphaned Azure resources must be deleted manually via the portal.
    """
    state = StateManager()
    deployments = state.all

    if not deployments:
        print_info("Nothing to clean — no deployments tracked")
        return

    print_warning(f"Saboteur is tracking {len(deployments)} deployment(s):")
    for dep in deployments:
        out.print(f"  [cyan]{dep.scenario_id}[/cyan] ({dep.status})")

    out.print()
    print_warning(
        "This will remove all resources from local Terraform state and clear deployment tracking.\n"
        "It does NOT delete anything from Azure — orphaned resources must be cleaned up manually in the portal."
    )

    total_removed = 0
    for dep in deployments:
        tf = TerraformRunner(scenario_id=dep.scenario_id)
        if not tf.init():
            print_error(f"Failed to init workspace for {dep.scenario_id}")
            continue

        resources = tf.state_list()
        if resources:
            print_warning(f"Workspace '{dep.scenario_id}' contains {len(resources)} resource(s):")
            for r in resources:
                out.print(f"  [dim]{r}[/dim]")
            for resource in resources:
                if tf.state_rm(resource):
                    total_removed += 1
                    print_info(f"Removed from state: {resource}")
                else:
                    print_error(f"Failed to remove: {resource}")

        tf._delete_workspace()
        state.remove(dep.scenario_id)

    tf_default = TerraformRunner()
    tf_default.clean_chain_tf()

    print_success(
        f"Local cleanup complete — removed {total_removed} resource(s) from Terraform state, "
        f"cleared {len(deployments)} deployment(s) from tracking"
    )
    print_warning("Remember to delete orphaned resources in the Azure portal")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@app.command()
def status() -> None:
    """Show all tracked deployments."""
    state = StateManager()
    deployments = state.all
    if not deployments:
        print_info("No deployments tracked")
        return

    status_styles = {"deployed": "green", "failed": "red", "deploying": "yellow"}

    for dep in deployments:
        style = status_styles.get(dep.status, "white")
        chain_str = " → ".join(dep.chain) if dep.chain else "infra-only"
        out.print(
            f"  [{style}]{dep.status:<10}[/{style}] "
            f"[cyan]{dep.scenario_id}[/cyan]  "
            f"{chain_str}  ({dep.region}, {dep.created_at})"
        )


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@app.command()
def validate(
    flag: str = typer.Argument(..., help="Flag string to validate"),
    instance: Optional[str] = typer.Option(None, "--instance", "-i", help="Scenario ID"),
) -> None:
    """Check if a flag string is correct."""
    state = StateManager()

    if instance:
        deployment = state.get(instance)
        if not deployment:
            print_error(f"No deployment found: {instance}")
            raise typer.Exit(1)
        deployments = [deployment]
    else:
        deployments = state.active

    for dep in deployments:
        validator = FlagValidator(dep.flags)
        result = validator.validate(flag)
        if result.correct:
            print_success(result.message)
            return

    print_error("Incorrect flag. Keep trying!")


# ---------------------------------------------------------------------------
# list-modules
# ---------------------------------------------------------------------------

@app.command("list-modules")
def list_modules(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
) -> None:
    """Show all available vulnerability modules."""
    catalog = load_catalog(MODULES_DIR)
    modules = catalog.all

    if category:
        try:
            cat = ModuleCategory(category)
            modules = [m for m in modules if m.category == cat]
        except ValueError:
            print_error(f"Unknown category: {category}. Valid: {', '.join(c.value for c in ModuleCategory)}")
            raise typer.Exit(1)

    if not modules:
        print_info("No modules found")
        return

    from rich.table import Table

    table = Table(title="Vulnerability Modules")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Category", style="yellow")
    table.add_column("Requires", style="dim")
    table.add_column("Provides", style="green")
    for mod in modules:
        table.add_row(
            mod.id,
            mod.name,
            mod.category.value,
            ", ".join(mod.requires),
            ", ".join(mod.provides),
        )
    out.print(table)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _parse_categories(categories: str | None) -> list[ModuleCategory] | None:
    if not categories:
        return None
    result = []
    for c in categories.split(","):
        c = c.strip().lower()
        try:
            result.append(ModuleCategory(c))
        except ValueError:
            print_warning(f"Unknown category '{c}', skipping")
    return result or None
