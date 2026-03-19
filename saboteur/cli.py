"""CLI commands for AZSaboteur."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from saboteur.config import DeploymentState, StateManager
from saboteur.deploy.terraform import TerraformRunner
from saboteur.modules.base import ModuleCategory
from saboteur.modules.catalog import load_catalog
from saboteur.scenario.engine import ScenarioConfig, ScenarioEngine
from saboteur.scenario.validator import FlagValidator
from saboteur.utils.azure_auth import accept_kali_terms, get_subscription_id
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
)

MODULES_DIR = Path(__file__).resolve().parent.parent / "modules"


def _load_engine(seed: int | None = None) -> ScenarioEngine:
    catalog = load_catalog(MODULES_DIR)
    if len(catalog) == 0:
        print_error("No vulnerability modules found. Add YAML definitions to modules/")
        raise typer.Exit(1)
    return ScenarioEngine(catalog, seed=seed)


@app.command()
def generate(
    chain_length: int = typer.Option(3, "--chain-length", "-n", help="Number of steps in the attack chain"),
    categories: Optional[str] = typer.Option(None, "--categories", "-c", help="Comma-separated categories: web,identity,compute,storage,networking"),
    region: str = typer.Option("westeurope", "--region", "-r", help="Azure region"),
    seed: Optional[int] = typer.Option(None, "--seed", "-s", help="Random seed for reproducibility"),
    output_file: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path (JSON)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full chain details"),
) -> None:
    """Generate a scenario without deploying (dry run)."""
    print_banner()

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
    if verbose:
        print_chain_verbose(chain_data)
    else:
        print_chain_summary(chain_data)
    print_info(f"Scenario ID: {scenario.scenario_id}")

    if output_file:
        data = scenario.to_terraform_vars()
        data["graph"] = scenario.graph.to_dict()
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)
        print_success(f"Scenario written to {output_file}")


@app.command()
def deploy(
    chain_length: int = typer.Option(3, "--chain-length", "-n", help="Number of steps in the attack chain"),
    categories: Optional[str] = typer.Option(None, "--categories", "-c", help="Comma-separated categories"),
    region: str = typer.Option("westeurope", "--region", "-r", help="Azure region"),
    seed: Optional[int] = typer.Option(None, "--seed", "-s", help="Random seed"),
    auto_approve: bool = typer.Option(False, "--auto-approve", "-y", help="Skip confirmation"),
    subscription_id: Optional[str] = typer.Option(None, "--subscription", help="Azure subscription ID (auto-detected from az cli if omitted)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Stream Terraform output for debugging"),
) -> None:
    """Generate and deploy a scenario to Azure."""
    print_banner()

    sub_id = subscription_id or get_subscription_id()
    if not sub_id:
        print_error("No Azure subscription found. Run 'az login' or pass --subscription.")
        raise typer.Exit(1)

    cat_list = _parse_categories(categories)
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
    if verbose:
        print_chain_verbose(chain_data)
    else:
        print_chain_summary(chain_data)
    print_info(f"Scenario ID: {scenario.scenario_id}")

    if not auto_approve:
        proceed = typer.confirm("Proceed with deployment?")
        if not proceed:
            raise typer.Abort()

    if not accept_kali_terms():
        print_error("Failed to accept Kali Linux marketplace terms. Check your Azure permissions.")
        raise typer.Exit(1)

    tf = TerraformRunner(verbose=verbose)
    tf_vars = scenario.to_terraform_vars()
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

    deployment.status = "deployed"
    state.add(deployment)

    tf_outputs = tf.output()
    kali_ip = tf_outputs.get("kali_public_ip", {}).get("value", "<pending>")

    kali_user = scenario.kali_credentials["username"]
    kali_pass = scenario.kali_credentials["password"]
    print_success("Deployment complete!")
    print_mission_briefing(
        target=f"{kali_ip} (Kali box)",
        objective="Scan the network from the Kali box, exploit the chain, and find the flags.",
        connection_info=f"xfreerdp /v:{kali_ip} /u:{kali_user} /p:{kali_pass} /cert:ignore",
    )


@app.command()
def destroy(
    instance: str = typer.Argument(..., help="Scenario ID to destroy"),
    auto_approve: bool = typer.Option(False, "--auto-approve", "-y", help="Skip confirmation"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Stream Terraform output for debugging"),
) -> None:
    """Tear down a deployed scenario."""
    state = StateManager()
    deployment = state.get(instance)
    if not deployment:
        print_error(f"No deployment found with ID: {instance}")
        raise typer.Exit(1)

    if deployment.status == "failed":
        print_warning(f"Deployment {instance} was in a failed state — cleaning up.")

    if not auto_approve:
        proceed = typer.confirm(f"Destroy deployment {instance}?")
        if not proceed:
            raise typer.Abort()

    tf = TerraformRunner(verbose=verbose)
    if tf.destroy(auto_approve=True):
        state.remove(instance)
        print_success(f"Deployment {instance} destroyed")
    else:
        print_error("Destroy failed — you may need to clean up manually via the Azure portal or 'terraform destroy' in terraform/")
        raise typer.Exit(1)


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
        chain_str = " → ".join(dep.chain)
        out.print(
            f"  [{style}]{dep.status:<10}[/{style}] "
            f"[cyan]{dep.scenario_id}[/cyan]  "
            f"{chain_str}  ({dep.region}, {dep.created_at})"
        )


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
