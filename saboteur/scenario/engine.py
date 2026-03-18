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
        entry = self.graph.entry_modules()[0]
        return {
            "target": self.resource_names.get(entry.id, self.scenario_id),
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
        """Build a random attack chain of exactly ``chain_length`` steps.

        Uses DFS with backtracking over randomly-shuffled candidates so each
        run (with a different seed) produces a different chain.  Raises
        ``ValueError`` only when no chain of the requested length exists at all.
        """
        entry_points = self.catalog.entry_points(categories=config.categories)
        if not entry_points:
            raise ValueError("No entry point modules available for the given filters.")

        # Randomise entry point order so different seeds give different chains
        self.rng.shuffle(entry_points)

        for entry in entry_points:
            result = self._extend_chain([entry], config)
            if len(result) >= config.chain_length:
                return result

        raise ValueError(
            f"Cannot build a chain of length {config.chain_length} "
            f"with the available modules and category filters. "
            f"Try a shorter chain or broader categories."
        )

    def _extend_chain(
        self, chain: list[VulnModule], config: ScenarioConfig
    ) -> list[VulnModule]:
        """Recursively extend the chain, backtracking on dead ends."""
        if len(chain) >= config.chain_length:
            return chain

        current = chain[-1]
        used_ids = {c.id for c in chain}
        candidates = [
            m for m in self.catalog.followers(current) if m.id not in used_ids
        ]

        if config.categories:
            filtered = [m for m in candidates if m.category in config.categories]
            if filtered:
                candidates = filtered

        # Randomise so backtracking explores a different order each run
        self.rng.shuffle(candidates)

        for candidate in candidates:
            result = self._extend_chain(chain + [candidate], config)
            if len(result) >= config.chain_length:
                return result

        return chain
