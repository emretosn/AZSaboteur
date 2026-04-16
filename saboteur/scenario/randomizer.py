"""Randomization for credentials, flags, resource names, and vulnerability parameters."""

from __future__ import annotations

import random
import secrets
import string


USERNAMES = [
    "svc_deploy", "app_admin", "backup_user", "webadmin", "api_service",
    "db_reader", "func_runner", "blob_writer", "kv_reader", "infra_bot",
]

# Weak passwords for entry-point modules — every password here is verified to
# exist in the NCSC 100k-most-used-passwords list (via SecLists). Players use
# hydra with the raw NCSC list at:
#   /usr/share/seclists/Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt
# All passwords also meet Azure VM complexity (3-of-4: lower, upper, digit, special).
WEAK_PASSWORDS = [
    "Password1", "Passw0rd", "Welcome1", "Password123",
    "Qwerty123", "Pa55word", "Letmein1", "Password01",
    "Welcome123", "Admin123",
]


class Randomizer:
    """Generates randomized values for scenario deployment."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def _hex(self, length: int = 8) -> str:
        return secrets.token_hex(length // 2 + 1)[:length]

    def flag_string(self) -> str:
        return f"AZS_F{{{self._hex(12)}}}"

    def scenario_id(self) -> str:
        return f"AZSaboteur-{self._hex(8)}"

    def resource_name(self, module_id: str) -> str:
        short = module_id.lower().replace("-", "").replace("_", "")[:8]
        return f"azs-{short}-{self._hex(6)}"

    def credentials(self, count: int = 1, entry_steps: set[int] | None = None) -> dict[str, str]:
        """Generate random username/password pairs.

        Steps in ``entry_steps`` get weak, brute-forceable passwords.
        All other steps get strong random passwords.
        """
        entry_steps = entry_steps or set()
        creds = {}
        used_usernames: set[str] = set()
        for i in range(count):
            available = [u for u in USERNAMES if u not in used_usernames]
            if not available:
                available = USERNAMES
            username = self.rng.choice(available)
            used_usernames.add(username)
            password = self.weak_password() if i in entry_steps else self._password()
            creds[f"step_{i}_username"] = username
            creds[f"step_{i}_password"] = password
        return creds

    def weak_password(self) -> str:
        """Return a weak, brute-forceable password from a common wordlist."""
        return self.rng.choice(WEAK_PASSWORDS)

    def _password(self, length: int = 16) -> str:
        lower = string.ascii_lowercase
        upper = string.ascii_uppercase
        digits = string.digits
        special = "!@#$%&*"
        all_chars = lower + upper + digits + special
        # Guarantee at least one character from each class to meet Azure complexity
        password = [
            secrets.choice(lower),
            secrets.choice(upper),
            secrets.choice(digits),
            secrets.choice(special),
        ]
        password += [secrets.choice(all_chars) for _ in range(length - 4)]
        self.rng.shuffle(password)
        return "".join(password)

    def sql_table_name(self) -> str:
        return f"tbl_{self._hex(6)}"

    def api_path(self) -> str:
        return f"/api/{self._hex(6)}"

    def blob_name(self) -> str:
        return f"data-{self._hex(6)}.json"
