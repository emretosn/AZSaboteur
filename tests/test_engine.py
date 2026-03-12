"""Tests for the scenario generation engine."""

from pathlib import Path

from saboteur.modules.catalog import load_catalog
from saboteur.scenario.engine import ScenarioConfig, ScenarioEngine

MODULES_DIR = Path(__file__).resolve().parent.parent / "modules"


class TestScenarioEngine:
    def _engine(self, seed: int = 42) -> ScenarioEngine:
        catalog = load_catalog(MODULES_DIR)
        return ScenarioEngine(catalog, seed=seed)

    def test_generate_basic_chain(self):
        engine = self._engine()
        config = ScenarioConfig(chain_length=3, seed=42)
        scenario = engine.generate(config)
        assert len(scenario.graph.nodes) >= 2
        assert len(scenario.graph.nodes) <= 3
        assert scenario.scenario_id.startswith("AZSaboteur-")

    def test_flags_format(self):
        engine = self._engine()
        config = ScenarioConfig(chain_length=3, seed=42)
        scenario = engine.generate(config)
        for flag in scenario.flags.values():
            assert flag.startswith("AZS_F{")

    def test_deterministic_with_seed(self):
        config = ScenarioConfig(chain_length=3, seed=123)
        s1 = self._engine(123).generate(config)
        s2 = self._engine(123).generate(config)
        chain1 = list(s1.graph.nodes.keys())
        chain2 = list(s2.graph.nodes.keys())
        assert chain1 == chain2

    def test_terraform_vars(self):
        engine = self._engine()
        config = ScenarioConfig(chain_length=3, seed=42)
        scenario = engine.generate(config)
        tf_vars = scenario.to_terraform_vars()
        assert "scenario_id" in tf_vars
        assert "chain" in tf_vars
        assert "flags" in tf_vars
        assert "credentials" in tf_vars

    def test_player_briefing(self):
        engine = self._engine()
        config = ScenarioConfig(chain_length=3, seed=42)
        scenario = engine.generate(config)
        briefing = scenario.player_briefing()
        assert "target" in briefing
        assert "objective" in briefing

    def test_category_filter(self):
        engine = self._engine()
        from saboteur.modules.base import ModuleCategory
        config = ScenarioConfig(
            chain_length=2,
            categories=[ModuleCategory.WEB, ModuleCategory.STORAGE],
            seed=42,
        )
        scenario = engine.generate(config)
        for mid in scenario.graph.nodes:
            mod = scenario.graph.get_module(mid)
            assert mod.category in [ModuleCategory.WEB, ModuleCategory.STORAGE]
