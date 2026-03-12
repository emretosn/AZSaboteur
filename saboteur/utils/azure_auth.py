"""Azure authentication helpers."""

from __future__ import annotations

import subprocess
import json


def check_azure_cli() -> bool:
    """Check if the Azure CLI is installed and logged in."""
    try:
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_subscription_id() -> str | None:
    """Get the current Azure subscription ID."""
    try:
        result = subprocess.run(
            ["az", "account", "show", "--query", "id", "-o", "tsv"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def get_tenant_id() -> str | None:
    """Get the current Azure tenant ID."""
    try:
        result = subprocess.run(
            ["az", "account", "show", "--query", "tenantId", "-o", "tsv"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def get_account_info() -> dict | None:
    """Get full Azure account info."""
    try:
        result = subprocess.run(
            ["az", "account", "show", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return None


def accept_marketplace_terms(publisher: str, offer: str, plan: str) -> bool:
    """Accept Azure Marketplace image terms. Idempotent — safe to call if already accepted."""
    try:
        result = subprocess.run(
            ["az", "vm", "image", "terms", "accept",
             "--publisher", publisher, "--offer", offer, "--plan", plan],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def accept_kali_terms() -> bool:
    """Accept Kali Linux marketplace terms."""
    return accept_marketplace_terms("kali-linux", "kali", "kali-2025-2")
