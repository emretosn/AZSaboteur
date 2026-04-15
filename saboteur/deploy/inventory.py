"""Dynamic Ansible inventory generator from Terraform outputs."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

import yaml

ANSIBLE_DIR = Path(__file__).resolve().parent.parent.parent / "ansible"

# Module IDs that deploy VMs requiring SSH provisioning
VM_MODULES = {
    "WEB-SSRF",
    "WEB-SQLI",
    "WEB-CMDI",
    "WEB-GITEXPOSE",
    "NET-NSG-OPEN",
    "NET-MGMT-EXPOSED",
    "CMP-IMDS",
    "CMP-RUNCOMMAND",
}


def _ansible_group_name(ansible_role: str) -> str:
    """Convert an ansible role path like 'roles/vulnerable-flask-app' to a group name."""
    name = ansible_role.rsplit("/", 1)[-1]
    return name.replace("-", "_")


def _extract_tf_value(output: dict[str, Any] | Any) -> Any:
    """Unwrap Terraform output JSON (handles {value: X} nesting)."""
    if isinstance(output, dict) and "value" in output:
        return output["value"]
    return output


def generate_inventory(
    tf_outputs: dict[str, Any],
    chain_steps: list[dict[str, Any]],
    credentials: dict[str, str],
    flags: dict[str, str],
    kali_password: str,
) -> Path:
    """Generate ansible/inventory/hosts.yml from Terraform outputs and chain data.

    Args:
        tf_outputs: Parsed output from ``terraform output -json``.
        chain_steps: Chain config list enriched with ``ansible_role``.
            Each item: {"step": 0, "module_id": "WEB-SSRF",
                        "ansible_role": "roles/vulnerable-flask-app", ...}
        credentials: Credential dict (step_0_username, step_0_password, …).
        flags: Flag dict ("0": "AZS_F{…}", "1": "AZS_F{…}").
        kali_password: SSH password for the Kali jump host.

    Returns:
        Path to the written inventory file.
    """
    kali_ip = _extract_tf_value(tf_outputs.get("kali_public_ip", ""))
    chain_outputs = _extract_tf_value(tf_outputs.get("chain_outputs", {}))

    # Write the Kali SSH password to a file so sshpass -f avoids shell escaping issues
    inventory_dir = ANSIBLE_DIR / "inventory"
    inventory_dir.mkdir(parents=True, exist_ok=True)
    kali_pass_file = inventory_dir / ".kali_pass"
    kali_pass_file.write_text(kali_password)
    kali_pass_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600

    children: dict[str, Any] = {}

    for step in chain_steps:
        idx = step["step"]
        module_id = step["module_id"]
        ansible_role = step.get("ansible_role", "")
        group = _ansible_group_name(ansible_role)
        step_outputs = chain_outputs.get(str(idx), {})
        private_ip = step_outputs.get("private_ip")
        step_flag = flags.get(str(idx), "")

        host_vars: dict[str, Any] = {
            "flag": step_flag,
            "next_step_secret": step_flag,
            "step_index": idx,
        }

        is_vm = module_id in VM_MODULES and private_ip
        if is_vm:
            username = credentials.get(f"step_{idx}_username", "")
            password = credentials.get(f"step_{idx}_password", "")
            proxy_cmd = (
                f"sshpass -f {kali_pass_file} ssh "
                f"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
                f"-W %h:%p kali@{kali_ip}"
            )
            host_vars.update(
                {
                    "ansible_host": private_ip,
                    "ansible_user": username,
                    "ansible_password": password,
                    "ansible_ssh_common_args": (
                        f'-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '
                        f'-o ProxyCommand="{proxy_cmd}"'
                    ),
                    "admin_username": username,
                }
            )
        else:
            host_vars["ansible_connection"] = "local"

        # Merge any extra outputs (key_vault_name, storage_account_name, etc.)
        for key, val in step_outputs.items():
            if key not in ("private_ip", "vm_id"):
                host_vars[key] = val

        if group not in children:
            children[group] = {"hosts": {}}
        children[group]["hosts"][f"step_{idx}"] = host_vars

    inventory: dict[str, Any] = {
        "all": {
            "vars": {
                "ansible_ssh_common_args": (
                    "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
                ),
                "ansible_become": True,
                "ansible_become_method": "sudo",
            },
            "children": children,
        }
    }

    inventory_dir = ANSIBLE_DIR / "inventory"
    inventory_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = inventory_dir / "hosts.yml"
    inventory_path.write_text(yaml.dump(inventory, default_flow_style=False, sort_keys=False))
    return inventory_path
