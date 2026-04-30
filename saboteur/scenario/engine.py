"""Scenario generation engine — assembles attack chains from the module catalog."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from saboteur.modules.base import ModuleCategory, VulnModule
from saboteur.modules.catalog import ModuleCatalog
from saboteur.scenario.graph import ScenarioGraph
from saboteur.scenario.randomizer import Randomizer


@dataclass
class ScenarioConfig:
    """Player-selected options for scenario generation."""

    chain_length: int = 3
    categories: list[ModuleCategory] | None = None
    region: str = "westeurope"
    subscription_id: str = ""
    seed: int | None = None
    explicit_chain: list[str] | None = None
    exclude: list[str] | None = None


# Modules that cannot be deployed on Microsoft-managed (MCAP) subscriptions
# due to enforced tenant policies (no shared key access, no Entra app creation).
MCAP_BLOCKED = [
    "IAM-OVERPERM-SP",
    "IAM-APPREG-SECRET",
    "STR-SAS-OVERPERM",
    "STR-COSMOSDB-KEY",
]


@dataclass
class Scenario:
    """A fully generated scenario ready for deployment."""

    scenario_id: str
    config: ScenarioConfig
    graph: ScenarioGraph
    flags: dict[int, str]
    credentials: dict[str, str]
    resource_names: dict[str, str]
    kali_credentials: dict[str, str]

    def to_terraform_vars(self) -> dict[str, Any]:
        """Convert to a scenario.auto.tfvars.json structure."""
        chain_configs = []
        for i, node_id in enumerate(self.graph.topo_order()):
            module = self.graph.get_module(node_id)
            chain_configs.append(
                {
                    "module": module.terraform_module,
                    "module_id": module.id,
                    "step": i,
                    "config": {
                        "resource_prefix": self.resource_names.get(
                            module.id, self.scenario_id
                        ),
                    },
                }
            )

        return {
            "scenario_id": self.scenario_id,
            "region": self.config.region,
            "subscription_id": self.config.subscription_id,
            "kali_admin_username": self.kali_credentials["username"],
            "kali_admin_password": self.kali_credentials["password"],
            "chain": chain_configs,
            "credentials": self.credentials,
            "flags": {str(k): v for k, v in self.flags.items()},
        }

    def player_briefing(self) -> dict[str, str]:
        """Generate the mission briefing for the player."""
        entries = self.graph.entry_modules()
        target = self.resource_names.get(entries[0].id, self.scenario_id) if entries else self.scenario_id
        return {
            "target": target,
            "objective": "Find the flag hidden in the Azure environment.",
            "chain_length": str(len(self.graph.nodes)),
        }


class ScenarioEngine:
    """Generates attack chain scenarios from a module catalog."""

    def __init__(self, catalog: ModuleCatalog, seed: int | None = None) -> None:
        self.catalog = catalog
        self.rng = random.Random(seed)

    def generate(self, config: ScenarioConfig) -> Scenario:
        """Generate a complete scenario from the given configuration."""
        if config.seed is not None:
            self.rng = random.Random(config.seed)

        chain = self._build_chain(config)
        randomizer = Randomizer(self.rng)
        scenario_id = randomizer.scenario_id()

        flags = {}
        for i in range(len(chain)):
            flags[i] = randomizer.flag_string()

        credentials = randomizer.credentials(len(chain))
        resource_names = {mod.id: randomizer.resource_name(mod.id) for mod in chain}

        graph = ScenarioGraph.from_chain(chain)

        kali_credentials = {
            "username": "kali",
            "password": randomizer._password(),
        }

        return Scenario(
            scenario_id=scenario_id,
            config=config,
            graph=graph,
            flags=flags,
            credentials=credentials,
            resource_names=resource_names,
            kali_credentials=kali_credentials,
        )

    def _build_chain(self, config: ScenarioConfig) -> list[VulnModule]:
        """Build an attack chain — either from an explicit list or randomly."""
        if config.explicit_chain:
            return self._build_explicit_chain(config.explicit_chain)

        if config.chain_length == 0:
            return []

        excluded = set(config.exclude or [])

        entry_points = [
            m for m in self.catalog.entry_points(categories=config.categories)
            if m.id not in excluded
        ]
        if not entry_points:
            raise ValueError("No entry point modules available for the given filters.")

        # Randomise entry point order so different seeds give different chains
        self.rng.shuffle(entry_points)

        for entry in entry_points:
            result = self._extend_chain([entry], config, excluded)
            if len(result) >= config.chain_length:
                return result

        raise ValueError(
            f"Cannot build a chain of length {config.chain_length} "
            f"with the available modules and category filters. "
            f"Try a shorter chain or broader categories."
        )

    def _build_explicit_chain(self, module_ids: list[str]) -> list[VulnModule]:
        """Resolve and validate a user-specified chain of module IDs."""
        if not module_ids:
            return []

        modules: list[VulnModule] = []
        for mid in module_ids:
            mod = self.catalog.get(mid)
            if mod is None:
                available = ", ".join(m.id for m in self.catalog.all)
                raise ValueError(
                    f"Unknown module '{mid}'. Available modules: {available}"
                )
            modules.append(mod)

        # First module must be an entry point
        if not modules[0].is_entry_point:
            raise ValueError(
                f"First module '{modules[0].id}' is not an entry point "
                f"(requires {modules[0].requires}, but entry points must only "
                f"require 'network_access')."
            )

        # Validate each link in the chain
        for i in range(1, len(modules)):
            prev, curr = modules[i - 1], modules[i]
            if not curr.can_follow(prev):
                raise ValueError(
                    f"Invalid chain link: '{curr.id}' requires {curr.requires} "
                    f"but '{prev.id}' provides {prev.provides}."
                )

        return modules

    def _extend_chain(
        self, chain: list[VulnModule], config: ScenarioConfig,
        excluded: set[str] | None = None,
    ) -> list[VulnModule]:
        """Recursively extend the chain, backtracking on dead ends."""
        if len(chain) >= config.chain_length:
            return chain

        excluded = excluded or set()
        current = chain[-1]
        used_ids = {c.id for c in chain}
        candidates = [
            m for m in self.catalog.followers(current)
            if m.id not in used_ids and m.id not in excluded
        ]

        if config.categories:
            candidates = [m for m in candidates if m.category in config.categories]

        # Randomise so backtracking explores a different order each run
        self.rng.shuffle(candidates)

        for candidate in candidates:
            result = self._extend_chain(chain + [candidate], config, excluded)
            if len(result) >= config.chain_length:
                return result

        return chain
