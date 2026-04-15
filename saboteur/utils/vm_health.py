"""Post-deploy VM health checks — polls until VMs are ready."""

from __future__ import annotations

import json
import socket
import subprocess
import time

from saboteur.utils.output import console, print_error, print_success, print_warning

DEFAULT_TIMEOUT = 1800  # 30 minutes — Kali cloud-init installs heavy packages
POLL_INTERVAL = 20  # seconds between checks


def _run_vm_command(resource_group: str, vm_name: str, script: str) -> str | None:
    """Execute a script on the VM via az vm run-command and return stdout."""
    try:
        result = subprocess.run(
            [
                "az", "vm", "run-command", "invoke",
                "-g", resource_group,
                "-n", vm_name,
                "--command-id", "RunShellScript",
                "--scripts", script,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return data["value"][0].get("message", "")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, IndexError):
        return None


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
