"""Post-deploy VM health checks — polls until VMs are ready."""

from __future__ import annotations

import json
import socket
import subprocess
import time

from saboteur.utils.output import console, print_error, print_info, print_success, print_warning

DEFAULT_TIMEOUT = 1800  # 30 minutes — Kali cloud-init installs heavy packages
POLL_INTERVAL = 20  # seconds between checks
VM_START_TIMEOUT = 300  # 5 minutes — time to wait for a stopped VM to become reachable


def _run_az(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Run an az CLI command and return the result."""
    return subprocess.run(
        ["az", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_vm_command(resource_group: str, vm_name: str, script: str) -> str | None:
    """Execute a script on the VM via az vm run-command and return stdout."""
    try:
        result = _run_az(
            [
                "vm", "run-command", "invoke",
                "-g", resource_group,
                "-n", vm_name,
                "--command-id", "RunShellScript",
                "--scripts", script,
            ],
            timeout=120,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return data["value"][0].get("message", "")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, IndexError):
        return None


def get_vm_power_state(resource_group: str, vm_name: str) -> str | None:
    """Return the VM power state (e.g. 'VM running', 'VM deallocated') or None on error."""
    try:
        result = _run_az([
            "vm", "get-instance-view",
            "-g", resource_group,
            "-n", vm_name,
            "--query", "instanceView.statuses[?starts_with(code, 'PowerState/')].displayStatus | [0]",
            "-o", "tsv",
        ])
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def ensure_vm_running(resource_group: str, vm_name: str) -> bool:
    """Ensure the VM is running — start it if stopped/deallocated.

    Returns True if the VM is running (or was successfully started), False on failure.
    """
    power_state = get_vm_power_state(resource_group, vm_name)
    if power_state is None:
        print_error(f"Could not determine VM power state for {vm_name}")
        return False

    if power_state == "VM running":
        return True

    print_info(f"VM is '{power_state}' — starting...")
    try:
        result = _run_az(
            ["vm", "start", "-g", resource_group, "-n", vm_name],
            timeout=VM_START_TIMEOUT,
        )
        if result.returncode != 0:
            print_error(f"Failed to start VM: {result.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        print_error("VM start timed out")
        return False

    # Verify it's actually running now
    power_state = get_vm_power_state(resource_group, vm_name)
    if power_state == "VM running":
        print_success("VM is running")
        return True

    print_error(f"VM start succeeded but state is '{power_state}'")
    return False


def ensure_nsg_rules(resource_group: str, nsg_name: str) -> bool:
    """Ensure RDP and SSH inbound rules exist on the Kali NSG.

    Azure policies on managed subscriptions can auto-remove permissive NSG rules.
    This re-creates them if missing.
    Returns True if rules are in place, False on failure.
    """
    try:
        result = _run_az([
            "network", "nsg", "rule", "list",
            "-g", resource_group,
            "--nsg-name", nsg_name,
            "--query", "[].name",
            "-o", "tsv",
        ])
        if result.returncode != 0:
            return False
        existing_rules = set(result.stdout.strip().split())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

    rules_needed = []
    if "AllowRDP" not in existing_rules:
        rules_needed.append(("AllowRDP", "200", "3389"))
    if "AllowSSH" not in existing_rules:
        rules_needed.append(("AllowSSH", "210", "22"))

    if not rules_needed:
        return True

    for rule_name, priority, port in rules_needed:
        print_info(f"NSG rule '{rule_name}' missing — re-creating...")
        try:
            result = _run_az([
                "network", "nsg", "rule", "create",
                "-g", resource_group,
                "--nsg-name", nsg_name,
                "-n", rule_name,
                "--priority", priority,
                "--direction", "Inbound",
                "--access", "Allow",
                "--protocol", "Tcp",
                "--source-port-ranges", "*",
                "--destination-port-ranges", port,
                "--source-address-prefixes", "*",
                "--destination-address-prefixes", "*",
                "-o", "none",
            ], timeout=60)
            if result.returncode != 0:
                print_error(f"Failed to create NSG rule '{rule_name}': {result.stderr.strip()}")
                return False
            print_success(f"NSG rule '{rule_name}' created")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print_error(f"Timed out creating NSG rule '{rule_name}'")
            return False

    return True


def check_port(host: str, port: int, timeout: int = 5) -> bool:
    """Return True if a TCP connection to host:port succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def restart_xrdp(resource_group: str, vm_name: str) -> bool:
    """Restart the xRDP service on the VM via az run-command.

    Returns True if the restart command succeeded.
    """
    print_info("Restarting xRDP service...")
    output = _run_vm_command(resource_group, vm_name, "sudo systemctl restart xrdp")
    if output is not None:
        print_success("xRDP service restarted")
        return True
    print_error("Failed to restart xRDP service")
    return False


def wait_for_port(
    host: str,
    port: int,
    timeout: int = 60,
    label: str = "",
) -> bool:
    """Poll until a TCP port is reachable, with a spinner. Returns True on success."""
    desc = label or f"{host}:{port}"
    start = time.monotonic()
    with console.status(
        f"[bold blue]Waiting for {desc} to become reachable...",
        spinner="dots",
        spinner_style="blue",
    ):
        while True:
            if check_port(host, port):
                return True
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                return False
            remaining = timeout - elapsed
            time.sleep(min(5, remaining))


def _check_rdp_ready(resource_group: str, vm_name: str) -> bool:
    """Return True if cloud-init has finished (success or error) and xRDP is active."""
    output = _run_vm_command(
        resource_group,
        vm_name,
        "cloud-init status 2>/dev/null; echo '---'; systemctl is-active xrdp 2>/dev/null",
    )
    if output is None:
        return False
    # cloud-init reports "done" on success, "error" on partial failure — both mean it's finished
    cloud_init_finished = "status: done" in output or "status: error" in output
    xrdp_active = output.split("---")[-1].strip().startswith("active")
    return cloud_init_finished and xrdp_active


def wait_for_ssh(
    host: str,
    port: int = 22,
    timeout: int = 600,
) -> bool:
    """Block until SSH is reachable on the given host, showing a spinner.

    Uses a simple TCP connect check.  Returns True if reachable, False on timeout.
    """
    start = time.monotonic()

    with console.status(
        f"[bold blue]Waiting for SSH on {host}:{port}...",
        spinner="dots",
        spinner_style="blue",
    ):
        while True:
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                break

            try:
                with socket.create_connection((host, port), timeout=5):
                    minutes, seconds = divmod(int(elapsed), 60)
                    time_str = f"{minutes}m{seconds:02d}s" if minutes else f"{seconds}s"
                    print_success(f"SSH reachable on {host} (took {time_str})")
                    return True
            except (socket.timeout, ConnectionRefusedError, OSError):
                pass

            remaining = timeout - elapsed
            sleep_time = min(10, remaining)
            if sleep_time > 0:
                time.sleep(sleep_time)

    print_warning(f"SSH on {host} not reachable after {timeout}s — Ansible may fail to connect.")
    return False


def wait_for_rdp(
    resource_group: str,
    vm_name: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> bool:
    """Block until the Kali box is ready for RDP, showing a spinner.

    Returns True if ready, False if timed out.
    """
    start = time.monotonic()

    with console.status(
        "[bold blue]Waiting for Kali desktop to be ready (installing xRDP + xfce4)...",
        spinner="dots",
        spinner_style="blue",
    ):
        while True:
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                break

            if _check_rdp_ready(resource_group, vm_name):
                minutes, seconds = divmod(int(elapsed), 60)
                time_str = f"{minutes}m{seconds:02d}s" if minutes else f"{seconds}s"
                print_success(f"Kali desktop ready! (took {time_str})")
                return True

            remaining = timeout - elapsed
            sleep_time = min(POLL_INTERVAL, remaining)
            if sleep_time > 0:
                time.sleep(sleep_time)

    print_warning(
        "Kali desktop setup is taking longer than expected.\n"
        "It may still be installing — try connecting in a few minutes."
    )
    return False
