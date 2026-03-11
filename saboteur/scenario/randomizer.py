"""Randomization for credentials, flags, resource names, and vulnerability parameters."""

from __future__ import annotations

import random
import secrets
import string


USERNAMES = [
    "svc_deploy", "app_admin", "backup_user", "webadmin", "api_service",
    "db_reader", "func_runner", "blob_writer", "kv_reader", "infra_bot",
]


class Randomizer:
    """Generates randomized values for scenario deployment."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def _hex(self, length: int = 8) -> str:
        return secrets.token_hex(length // 2 + 1)[:length]

    def flag_string(self) -> str:
        return f"AZS_F_{self._hex(12)}"

    def scenario_id(self) -> str:
        return f"AZSaboteur-{self._hex(8)}"

    def resource_name(self, module_id: str) -> str:
        short = module_id.lower().replace("-", "").replace("_", "")[:8]
        return f"azs-{short}-{self._hex(6)}"

    def credentials(self, count: int = 1) -> dict[str, str]:
        """Generate random username/password pairs."""
        creds = {}
        used_usernames: set[str] = set()
        for i in range(count):
            available = [u for u in USERNAMES if u not in used_usernames]
            if not available:
                available = USERNAMES
            username = self.rng.choice(available)
            used_usernames.add(username)
            password = self._password()
            creds[f"step_{i}_username"] = username
            creds[f"step_{i}_password"] = password
        return creds

    def _password(self, length: int = 16) -> str:
        chars = string.ascii_letters + string.digits + "!@#$%&*"
        return "".join(secrets.choice(chars) for _ in range(length))

    def sql_table_name(self) -> str:
        return f"tbl_{self._hex(6)}"

    def api_path(self) -> str:
        return f"/api/{self._hex(6)}"

    def blob_name(self) -> str:
        return f"data-{self._hex(6)}.json"
