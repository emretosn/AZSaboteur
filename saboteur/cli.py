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
from saboteur.utils.azure_auth import accept_kali_terms, find_kali_golden_image, get_subscription_id
from saboteur.utils.vm_health import (
    check_port,
    ensure_nsg_rules,
    ensure_vm_running,
    restart_xrdp,
    wait_for_port,
    wait_for_rdp,
)
from saboteur.utils.output import (
    console as out,
    print_banner,
    print_chain_summary,
    print_chain_table,
    print_chain_verbose,
    print_error,
    print_flag_panel,
    print_flag_status,
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
    chain: Optional[str] = typer.Option(None, "--chain", help="Explicit chain of module IDs (comma-separated, e.g. NET-MGMT-EXPOSED,CMP-IMDS,STR-KEYVAULT-POLICY)"),
    exclude: Optional[str] = typer.Option(None, "--exclude", "-x", help="Exclude module IDs from random generation (comma-separated, or 'mcap' to exclude all MCAP-incompatible modules)"),
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
        chain_ids = None
        exclude_ids = cfg.get("exclude")
    else:
        cat_list = _parse_categories(categories)
        chain_ids = _parse_chain(chain)
        exclude_ids = _parse_exclude(exclude)

    config = ScenarioConfig(
        chain_length=len(chain_ids) if chain_ids else chain_length,
        categories=cat_list,
        region=region,
        seed=seed,
        explicit_chain=chain_ids,
        exclude=exclude_ids,
    )

    engine = _load_engine(seed)
    try:
        scenario = engine.generate(config)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None

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
    chain: Optional[str] = typer.Option(None, "--chain", help="Explicit chain of module IDs (comma-separated, e.g. NET-MGMT-EXPOSED,CMP-IMDS,STR-KEYVAULT-POLICY)"),
    exclude: Optional[str] = typer.Option(None, "--exclude", "-x", help="Exclude module IDs from random generation (comma-separated, or 'mcap' to exclude all MCAP-incompatible modules)"),
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
        chain_ids = None
        exclude_ids = cfg.get("exclude")
    else:
        cat_list = _parse_categories(categories)
        chain_ids = _parse_chain(chain)
        exclude_ids = _parse_exclude(exclude)

    sub_id = subscription_id or get_subscription_id()
    if not sub_id:
        print_error("No Azure subscription found. Run 'az login' or pass --subscription.")
        raise typer.Exit(1)

    config = ScenarioConfig(
        chain_length=len(chain_ids) if chain_ids else chain_length,
        categories=cat_list,
        region=region,
        subscription_id=sub_id,
        seed=seed,
        explicit_chain=chain_ids,
        exclude=exclude_ids,
    )

    engine = _load_engine(seed)
    try:
        scenario = engine.generate(config)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None

    chain_data = [scenario.graph.get_module(mid).to_dict() for mid in scenario.graph.topo_order()]
    if chain_data:
        if verbose:
            print_chain_verbose(chain_data)
        else:
            print_chain_summary(chain_data)
    else:
        print_info("Infra-only mode — deploying Kali box and networking only")
    print_info(f"Scenario ID: {scenario.scenario_id}")

    ubuntu_fallback = False
    if not image:
        golden = find_kali_golden_image(sub_id)
        if golden:
            print_success(f"Found Kali golden image — skipping marketplace")
            image = golden
        elif not accept_kali_terms():
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
        if not image:
            # Kali marketplace images fail intermittently on some Azure subscriptions
            # (managed environments, marketplace purchase restrictions, propagation
            # delays for plan acceptance). Retry with an Ubuntu base image — the
            # cloud-init installs the same tools (nmap, hydra, etc.).
            print_warning(
                "Kali marketplace deployment failed — this is usually caused by Azure\n"
                "marketplace purchase restrictions on your subscription. Retrying with\n"
                "an Ubuntu base image (same tools will be installed via cloud-init)..."
            )
            ubuntu_fallback = True
            tf_vars["kali_use_ubuntu_fallback"] = True
            var_file = tf.write_var_file(tf_vars)
            tf.destroy(var_file=var_file)
            if not tf.apply(var_file=var_file):
                deployment.status = "failed"
                state.add(deployment)
                print_warning(
                    f"Deployment {scenario.scenario_id} failed. "
                    f"Run 'saboteur destroy {scenario.scenario_id}' to clean up."
                )
                raise typer.Exit(1)
        else:
            deployment.status = "failed"
            state.add(deployment)
            print_warning(
                f"Deployment {scenario.scenario_id} failed. "
                f"Run 'saboteur destroy {scenario.scenario_id}' to clean up."
            )
            raise typer.Exit(1)

    tf_outputs = tf.output()
    kali_ip = tf_outputs.get("kali_public_ip", {}).get("value", "<pending>")

    # Wait for Kali cloud-init to finish (installs SSH, xRDP, tools).
    # Must complete before Ansible can use Kali as an SSH jump host.
    kali_ready = True
    if not image:
        rg_name = f"rg-{scenario.scenario_id}"
        vm_name = f"vm-kali-{scenario.scenario_id}"
        kali_ready = wait_for_rdp(rg_name, vm_name)

    # --- Phase 2: Ansible provisioning ---
    if chain_data and kali_ready:
        chain_steps = []
        for i, node_id in enumerate(scenario.graph.topo_order()):
            module = scenario.graph.get_module(node_id)
            chain_steps.append({
                "step": i,
                "module_id": module.id,
                "ansible_role": module.ansible_role,
                "provides": module.provides,
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
    elif chain_data and not kali_ready:
        deployment.status = "deployed"
        state.add(deployment)
        print_warning(
            "Kali box not ready — skipped Ansible provisioning.\n"
            "Once the Kali box finishes booting, re-run Ansible manually:\n"
            "  ANSIBLE_CONFIG=ansible/ansible.cfg .venv/bin/ansible-playbook "
            "ansible/playbooks/site.yml -i ansible/inventory/hosts.yml"
        )
    else:
        deployment.status = "deployed"
        state.add(deployment)

    kali_user = scenario.kali_credentials["username"]
    kali_pass = scenario.kali_credentials["password"]
    print_success("Deployment complete!")
    if ubuntu_fallback:
        print_warning(
            "The attack box is running Ubuntu instead of Kali Linux because the Kali\n"
            "marketplace image could not be purchased on this Azure subscription. All\n"
            "the same pentesting tools (nmap, hydra, etc.) are being installed\n"
            "via cloud-init. To use Kali natively, build a golden image with:\n"
            "  cd packer && packer build kali.pkr.hcl\n"
            "  saboteur deploy --image <image_resource_id>"
        )
    box_label = "Ubuntu attack box" if ubuntu_fallback else "Kali box"
    conn_cmd = f"xfreerdp /v:{kali_ip} /u:{kali_user} /p:'{kali_pass}' /cert:ignore"
    if chain_data:
        print_mission_briefing(
            target=f"{kali_ip} ({box_label})",
            objective="Scan the network from the Kali box, exploit the chain, and find the flags.",
            connection_info=conn_cmd,
        )
    else:
        print_mission_briefing(
            target=f"{kali_ip} ({box_label})",
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
        FlagValidator.clear_state(instance)
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
def clean(
    instance: Optional[str] = typer.Argument(
        None, help="Scenario ID to clean (omit to clean all)"
    ),
) -> None:
    """Reset local Terraform state and saboteur tracking when destroy fails.

    Use this when 'saboteur destroy' can't delete resources (e.g. permission errors),
    or to remove stale local tracking for a deployment that no longer exists in Azure.
    It removes resources from Terraform state and clears saboteur deployment tracking.
    Orphaned Azure resources must be deleted manually via the portal.
    """
    state = StateManager()

    if instance:
        deployment = state.get(instance)
        if not deployment:
            print_error(f"No deployment found with ID: {instance}")
            raise typer.Exit(1)
        deployments = [deployment]
    else:
        deployments = state.all

    if not deployments:
        print_info("Nothing to clean — no deployments tracked")
        return

    print_warning(f"Cleaning {len(deployments)} deployment(s):")
    for dep in deployments:
        out.print(f"  [cyan]{dep.scenario_id}[/cyan] ({dep.status})")

    out.print()
    scope = f"'{instance}'" if instance else "all deployments"
    print_warning(
        f"This will remove {scope} from local Terraform state "
        "and clear deployment tracking.\n"
        "It does NOT delete anything from Azure — orphaned "
        "resources must be cleaned up manually in the portal."
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
        FlagValidator.clear_state(dep.scenario_id)
        state.remove(dep.scenario_id)

    # Only clean chain.tf when removing all deployments
    if not instance:
        tf_default = TerraformRunner()
        tf_default.clean_chain_tf()
        FlagValidator.clear_all_state()

    print_success(
        f"Local cleanup complete — removed {total_removed} resource(s) from Terraform state, "
        f"cleared {len(deployments)} deployment(s) from tracking"
    )
    if instance:
        print_info(
            f"Deployment '{instance}' removed from local tracking"
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
# connect
# ---------------------------------------------------------------------------

@app.command()
def connect(
    ctx: typer.Context,
    instance: Optional[str] = typer.Argument(None, help="Scenario ID to connect to"),
) -> None:
    """Connect to the Kali box of a deployed scenario.

    Ensures the VM is running, NSG rules are in place, and xRDP is healthy.
    Then prints the xfreerdp connection command.
    """
    state = StateManager()

    if instance is None and not _has_explicit_flags(ctx):
        deployments = state.active
        if not deployments:
            print_info("No active deployments to connect to")
            return
        if len(deployments) == 1:
            instance = deployments[0].scenario_id
        else:
            from saboteur.utils.prompts import prompt_select_instance
            cfg = prompt_select_instance("Select deployment to connect to:")
            instance = cfg["instance"]
            if not instance:
                return

    if not instance:
        print_error("No scenario ID provided. Usage: saboteur connect <SCENARIO_ID>")
        raise typer.Exit(1)

    deployment = state.get(instance)
    if not deployment:
        print_error(f"No deployment found with ID: {instance}")
        raise typer.Exit(1)

    if deployment.status != "deployed":
        print_error(
            f"Deployment {instance} is in '{deployment.status}' state — "
            "can only connect to deployed scenarios"
        )
        raise typer.Exit(1)

    # Read Terraform outputs for IP / resource names
    tf = TerraformRunner(scenario_id=instance)
    if not tf.init():
        raise typer.Exit(1)
    tf_outputs = tf.output()

    if not tf_outputs:
        print_error("Could not read Terraform outputs — is the infrastructure still deployed?")
        raise typer.Exit(1)

    kali_ip = tf_outputs.get("kali_public_ip", {}).get("value", "")
    kali_user = tf_outputs.get("kali_admin_username", {}).get("value", "kali")
    rg_name = tf_outputs.get("resource_group_name", {}).get("value", f"rg-{instance}")

    if not kali_ip:
        print_error("Could not determine Kali box IP from Terraform outputs")
        raise typer.Exit(1)

    # Recover kali password from tfvars
    var_file = tf.working_dir / "scenario.auto.tfvars.json"
    if not var_file.exists():
        print_error(
            f"Variable file not found: {var_file}\n"
            "Cannot recover credentials — a full redeploy is needed."
        )
        raise typer.Exit(1)

    with open(var_file) as f:
        tf_vars = json.load(f)

    kali_pass = tf_vars.get("kali_admin_password", "")
    if not kali_pass:
        print_error("Could not recover Kali password from tfvars — a full redeploy is needed.")
        raise typer.Exit(1)

    vm_name = f"vm-kali-{instance}"
    nsg_name = f"nsg-kali-{instance}"

    # Step 1: Ensure the VM is running
    print_info("Checking VM status...")
    if not ensure_vm_running(rg_name, vm_name):
        raise typer.Exit(1)

    # Step 2: Re-create the user account (Azure may wipe it after deallocation)
    print_info("Ensuring Kali user account exists...")
    _ensure_vm_user(rg_name, vm_name, kali_user, kali_pass)

    # Step 3: Ensure NSG rules allow RDP/SSH inbound
    print_info("Checking NSG rules...")
    if not ensure_nsg_rules(rg_name, nsg_name):
        print_warning("Could not verify NSG rules — connection may fail")

    # Step 4: Check RDP port, restart xRDP if needed
    if not check_port(kali_ip, 3389):
        print_warning("RDP port not reachable — attempting recovery...")
        restart_xrdp(rg_name, vm_name)
        if not wait_for_port(kali_ip, 3389, timeout=60, label="RDP"):
            print_error(
                "RDP port still unreachable after xRDP restart.\n"
                "The VM may need more time to boot. Try again in a minute."
            )
            raise typer.Exit(1)

    # Step 5: Fix startwm.sh if dbus-launch is missing (xfce4 crashes without it)
    _ensure_dbus_launch(rg_name, vm_name)

    print_success("Kali box is ready!")
    conn_cmd = (
        f"xfreerdp /v:{kali_ip} /u:{kali_user} /p:'{kali_pass}'"
        " /cert:ignore /dynamic-resolution"
    )
    print_mission_briefing(
        target=f"{kali_ip} (Kali box)",
        objective="Scan the network, exploit the chain, and capture the flags.",
        connection_info=conn_cmd,
    )


def _ensure_dbus_launch(resource_group: str, vm_name: str) -> None:
    """Ensure startwm.sh uses dbus-launch so xfce4-session survives reconnects."""
    from saboteur.utils.vm_health import _run_vm_command

    output = _run_vm_command(
        resource_group,
        vm_name,
        "grep -q 'dbus-launch' /etc/xrdp/startwm.sh && echo PATCHED || echo NEEDS_PATCH",
    )
    if output is not None and "PATCHED" in output and "NEEDS_PATCH" not in output:
        return

    print_info("Patching xRDP session to use dbus-launch...")
    _run_vm_command(
        resource_group,
        vm_name,
        "sudo sed -i "
        "'s|^exec xfce4-session|exec dbus-launch --exit-with-session xfce4-session|' "
        "/etc/xrdp/startwm.sh && sudo systemctl restart xrdp",
    )


def _ensure_vm_user(resource_group: str, vm_name: str, username: str, password: str) -> None:
    """Re-create the VM user account if it was wiped after deallocation.

    Azure's waagent may remove user accounts when a golden-image VM is
    stopped/deallocated and restarted.  ``az vm user update`` creates the
    user if missing, or resets the password if it already exists.
    """
    import subprocess

    result = subprocess.run(
        [
            "az", "vm", "user", "update",
            "--resource-group", resource_group,
            "--name", vm_name,
            "--username", username,
            "--password", password,
            "--no-wait",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print_warning(
            f"Could not reset VM user account — login may fail if the VM was deallocated.\n"
            f"  {result.stderr.strip()}"
        )


# ---------------------------------------------------------------------------
# credentials
# ---------------------------------------------------------------------------

@app.command()
def credentials(
    ctx: typer.Context,
    instance: Optional[str] = typer.Argument(None, help="Scenario ID"),
) -> None:
    """Print the Kali box connection credentials for a deployed scenario.

    Recovers the IP, username, and password from Terraform state so you can
    reconnect even after the original mission briefing has scrolled away.
    """
    state = StateManager()

    if instance is None and not _has_explicit_flags(ctx):
        deployments = state.active
        if not deployments:
            print_info("No active deployments")
            return
        if len(deployments) == 1:
            instance = deployments[0].scenario_id
        else:
            from saboteur.utils.prompts import prompt_select_instance
            cfg = prompt_select_instance("Select deployment:")
            instance = cfg["instance"]
            if not instance:
                return

    if not instance:
        print_error("No scenario ID provided. Usage: saboteur credentials <SCENARIO_ID>")
        raise typer.Exit(1)

    deployment = state.get(instance)
    if not deployment:
        print_error(f"No deployment found with ID: {instance}")
        raise typer.Exit(1)

    if deployment.status != "deployed":
        print_error(
            f"Deployment {instance} is in '{deployment.status}' state — "
            "can only show credentials for deployed scenarios"
        )
        raise typer.Exit(1)

    tf = TerraformRunner(scenario_id=instance)
    if not tf.init():
        raise typer.Exit(1)
    tf_outputs = tf.output()

    if not tf_outputs:
        print_error("Could not read Terraform outputs — is the infrastructure still deployed?")
        raise typer.Exit(1)

    kali_ip = tf_outputs.get("kali_public_ip", {}).get("value", "")
    kali_user = tf_outputs.get("kali_admin_username", {}).get("value", "kali")

    if not kali_ip:
        print_error("Could not determine Kali box IP from Terraform outputs")
        raise typer.Exit(1)

    var_file = tf.working_dir / "scenario.auto.tfvars.json"
    if not var_file.exists():
        print_error(
            f"Variable file not found: {var_file}\n"
            "Cannot recover credentials — a full redeploy is needed."
        )
        raise typer.Exit(1)

    with open(var_file) as f:
        tf_vars = json.load(f)

    kali_pass = tf_vars.get("kali_admin_password", "")
    if not kali_pass:
        print_error("Could not recover Kali password from tfvars — a full redeploy is needed.")
        raise typer.Exit(1)

    conn_cmd = (
        f"xfreerdp /v:{kali_ip} /u:{kali_user} /p:'{kali_pass}'"
        " /cert:ignore /dynamic-resolution"
    )
    print_mission_briefing(
        target=f"{kali_ip} (Kali box)",
        objective="Reconnect to your attack box using the credentials below.",
        connection_info=conn_cmd,
    )


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@app.command()
def validate(
    ctx: typer.Context,
    instance: Optional[str] = typer.Option(None, "--instance", "-i", help="Scenario ID"),
    reset: bool = typer.Option(False, "--reset", help="Clear saved progress and start fresh"),
) -> None:
    """Interactive flag validation menu.

    Submit captured flags and track your progress through the attack chain.
    Flags can be entered in any order. Progress is saved between sessions.
    Use --reset to clear saved progress without destroying the deployment.
    """
    if not sys.stdin.isatty():
        print_error("saboteur validate requires an interactive terminal.")
        raise typer.Exit(1)

    state = StateManager()

    # Always prompt for scenario selection first
    if instance:
        deployment = state.get(instance)
        if not deployment:
            print_error(f"No deployment found: {instance}")
            raise typer.Exit(1)
    else:
        deployments = state.active
        if not deployments:
            print_info("No active deployments to validate")
            return
        if len(deployments) == 1:
            deployment = deployments[0]
        else:
            from saboteur.utils.prompts import prompt_select_instance
            cfg = prompt_select_instance("Select deployment to validate:")
            sid = cfg["instance"]
            if not sid:
                return
            deployment = state.get(sid)
            if not deployment:
                return

    if not deployment.flags:
        print_info("This scenario has no flags to validate.")
        return

    if reset:
        FlagValidator.clear_state(deployment.scenario_id)
        print_success(f"Validation progress reset for {deployment.scenario_id}")

    validator = FlagValidator(deployment.flags, scenario_id=deployment.scenario_id)
    total = len(deployment.flags)

    message = ""
    if validator.solved:
        message = f"[dim]Restored progress: {validator.progress}[/dim]"

    if validator.is_complete:
        print_flag_panel(total, validator.solved)
        out.print(
            f"\n[bold green]🎉 All {total} flags already captured "
            f"— mission complete![/bold green]\n"
        )
        return

    # Track how many lines the panel + prompt occupy so we can overwrite
    panel_lines = print_flag_panel(total, validator.solved, message)

    while not validator.is_complete:
        try:
            submitted = out.input(
                "[bold cyan]Enter flag (or 'q' to quit):[/bold cyan] "
            )
        except (KeyboardInterrupt, EOFError):
            out.print()
            break

        submitted = submitted.strip()
        if submitted.lower() == "q":
            break

        if not submitted:
            # Erase the empty prompt line and reprint panel in place
            panel_lines = print_flag_panel(
                total, validator.solved, message, prev_lines=panel_lines + 1,
            )
            continue

        result = validator.validate(submitted)
        if result.correct and result.already_solved:
            message = f"[bold yellow]! {result.message}[/bold yellow]"
        elif result.correct:
            message = f"[bold green]✓ {result.message}[/bold green]"
        else:
            message = f"[bold red]✗ {result.message}[/bold red]"

        # +1 for the input/prompt line we need to overwrite too
        panel_lines = print_flag_panel(
            total, validator.solved, message, prev_lines=panel_lines + 1,
        )

    # Final output
    if validator.is_complete:
        # Overwrite the last panel + prompt
        print_flag_panel(total, validator.solved, prev_lines=panel_lines + 1)
        out.print(
            f"\n[bold green]🎉 Congratulations! All {total} "
            f"flags captured — mission complete![/bold green]\n"
        )
    else:
        out.print(f"\n{validator.progress}\n")


# ---------------------------------------------------------------------------
# reprovision
# ---------------------------------------------------------------------------

@app.command()
def reprovision(
    ctx: typer.Context,
    instance: Optional[str] = typer.Argument(None, help="Scenario ID to reprovision"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Stream Ansible output"),
) -> None:
    """Re-run Ansible provisioning on an existing deployment.

    Use this after changing Ansible roles, flags, or credentials without
    tearing down and redeploying the entire scenario. Much faster than a
    full destroy/deploy cycle (~1-2 min vs ~30 min).
    """
    state = StateManager()

    if instance is None and not _has_explicit_flags(ctx):
        deployments = state.active
        if not deployments:
            print_info("No active deployments to reprovision")
            return
        if len(deployments) == 1:
            instance = deployments[0].scenario_id
        else:
            from saboteur.utils.prompts import prompt_destroy_instance
            cfg = prompt_destroy_instance()
            instance = cfg["instance"]
            verbose = cfg.get("verbose", verbose)
            if not instance:
                return

    if not instance:
        print_error("No scenario ID provided. Usage: saboteur reprovision <SCENARIO_ID>")
        raise typer.Exit(1)

    deployment = state.get(instance)
    if not deployment:
        print_error(f"No deployment found with ID: {instance}")
        raise typer.Exit(1)

    if deployment.status != "deployed":
        print_error(f"Deployment {instance} is in '{deployment.status}' state — can only reprovision deployed scenarios")
        raise typer.Exit(1)

    if not deployment.chain:
        print_info("Infra-only deployment — nothing to reprovision")
        return

    print_info(f"Reprovisioning {instance}...")

    # Get Terraform outputs from the live workspace
    tf = TerraformRunner(verbose=verbose, scenario_id=instance)
    if not tf.init():
        raise typer.Exit(1)
    tf_outputs = tf.output()

    if not tf_outputs:
        print_error("Could not read Terraform outputs — is the infrastructure still deployed?")
        raise typer.Exit(1)

    # Load module catalog to resolve ansible_role for each chain step
    catalog = load_catalog(MODULES_DIR)

    chain_steps = []
    for i, module_id in enumerate(deployment.chain):
        module = catalog.get(module_id)
        if not module:
            print_error(f"Module '{module_id}' not found in catalog")
            raise typer.Exit(1)
        chain_steps.append({
            "step": i,
            "module_id": module.id,
            "ansible_role": module.ansible_role,
            "provides": module.provides,
        })

    # Re-generate credentials and flags from the stored deployment state
    # Flags come from deployment state; credentials come from the tfvars file
    tf_runner = TerraformRunner(scenario_id=instance)
    var_file = tf_runner.working_dir / "scenario.auto.tfvars.json"
    if not var_file.exists():
        print_error(f"Variable file not found: {var_file}\nCannot recover credentials — a full redeploy is needed.")
        raise typer.Exit(1)

    with open(var_file) as f:
        tf_vars = json.load(f)

    credentials = tf_vars.get("credentials", {})
    flags = tf_vars.get("flags", {})
    kali_password = tf_vars.get("kali_admin_password", "")

    if not kali_password:
        print_error("Could not recover Kali password from tfvars — a full redeploy is needed.")
        raise typer.Exit(1)

    ansible = AnsibleRunner(verbose=verbose)
    if ansible.provision_scenario(
        tf_outputs=tf_outputs,
        chain_steps=chain_steps,
        credentials=credentials,
        flags=flags,
        kali_password=kali_password,
    ):
        print_success(f"Reprovisioning complete for {instance}")
    else:
        print_warning(
            "Ansible provisioning failed. Check the target VMs are still running.\n"
            "Use -v for verbose output to debug."
        )
        raise typer.Exit(1)


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


def _parse_chain(chain: str | None) -> list[str] | None:
    if not chain:
        return None
    return [mid.strip().upper() for mid in chain.split(",") if mid.strip()]


def _parse_exclude(exclude: str | None) -> list[str] | None:
    if not exclude:
        return None
    from saboteur.scenario.engine import MCAP_BLOCKED
    if exclude.strip().lower() == "mcap":
        return list(MCAP_BLOCKED)
    return [mid.strip().upper() for mid in exclude.split(",") if mid.strip()]
