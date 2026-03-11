"""Tests for the attack graph."""

from saboteur.modules.base import ModuleCategory, VulnModule
from saboteur.scenario.graph import ScenarioGraph


def _mod(id: str, requires: list[str], provides: list[str]) -> VulnModule:
    return VulnModule(
        id=id,
        name=f"Test {id}",
        category=ModuleCategory.WEB,
        requires=requires,
        provides=provides,
    )


class TestScenarioGraph:
    def test_from_chain(self):
        chain = [
            _mod("A", ["network_access"], ["token"]),
            _mod("B", ["token"], ["secret"]),
            _mod("C", ["secret"], ["flag"]),
        ]
        graph = ScenarioGraph.from_chain(chain)
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2
        assert graph._entry_points == ["A"]
        assert graph.flag_nodes == ["C"]

    def test_topo_order(self):
        chain = [
            _mod("A", ["network_access"], ["token"]),
            _mod("B", ["token"], ["secret"]),
            _mod("C", ["secret"], ["flag"]),
        ]
        graph = ScenarioGraph.from_chain(chain)
        order = graph.topo_order()
        assert order == ["A", "B", "C"]

    def test_is_valid(self):
        chain = [
            _mod("A", ["network_access"], ["token"]),
            _mod("B", ["token"], ["secret"]),
        ]
        graph = ScenarioGraph.from_chain(chain)
        assert graph.is_valid() is True

    def test_to_dict(self):
        chain = [
            _mod("A", ["network_access"], ["token"]),
            _mod("B", ["token"], ["secret"]),
        ]
        graph = ScenarioGraph.from_chain(chain)
        data = graph.to_dict()
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        assert data["entry_points"] == ["A"]

    def test_player_briefing(self):
        chain = [
            _mod("A", ["network_access"], ["token"]),
            _mod("B", ["token"], ["secret"]),
        ]
        graph = ScenarioGraph.from_chain(chain)
        briefing = graph.to_player_briefing()
        assert "2 steps" in briefing
        assert "Test A" in briefing
        assert "🚩" in briefing
