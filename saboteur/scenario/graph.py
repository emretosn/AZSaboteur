"""Attack graph (DAG) logic for scenario representation."""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from saboteur.modules.base import VulnModule


@dataclass
class ScenarioGraph:
    """Directed Acyclic Graph representing an attack scenario."""

    nodes: dict[str, VulnModule] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)
    _entry_points: list[str] = field(default_factory=list)
    flag_nodes: list[str] = field(default_factory=list)

    def add_module(self, module: VulnModule, is_entry: bool = False, has_flag: bool = False) -> None:
        self.nodes[module.id] = module
        if is_entry:
            self._entry_points.append(module.id)
        if has_flag:
            self.flag_nodes.append(module.id)

    def add_edge(self, source_id: str, target_id: str) -> None:
        self.edges.append((source_id, target_id))

    def get_module(self, module_id: str) -> VulnModule:
        return self.nodes[module_id]

    def entry_modules(self) -> list[VulnModule]:
        return [self.nodes[mid] for mid in self._entry_points]

    def to_networkx(self) -> nx.DiGraph:
        """Convert to a NetworkX directed graph for analysis."""
        g = nx.DiGraph()
        for mid, module in self.nodes.items():
            g.add_node(mid, **module.to_dict())
        for src, dst in self.edges:
            g.add_edge(src, dst)
        return g

    def topo_order(self) -> list[str]:
        """Return module IDs in topological order."""
        g = self.to_networkx()
        return list(nx.topological_sort(g))

    def is_valid(self) -> bool:
        """Check that the graph is a valid DAG with reachable flag nodes."""
        g = self.to_networkx()
        if not nx.is_directed_acyclic_graph(g):
            return False
        for flag_id in self.flag_nodes:
            if flag_id not in g:
                return False
            for entry_id in self._entry_points:
                if not nx.has_path(g, entry_id, flag_id):
                    return False
        return True

    def to_dict(self) -> dict:
        return {
            "nodes": [m.to_dict() for m in self.nodes.values()],
            "edges": self.edges,
            "entry_points": self._entry_points,
            "flag_nodes": self.flag_nodes,
        }

    @classmethod
    def from_chain(cls, chain: list[VulnModule]) -> ScenarioGraph:
        """Build a linear graph from an ordered list of modules."""
        graph = cls()
        for i, module in enumerate(chain):
            is_entry = i == 0
            has_flag = i == len(chain) - 1
            graph.add_module(module, is_entry=is_entry, has_flag=has_flag)
            if i > 0:
                graph.add_edge(chain[i - 1].id, module.id)
        return graph

    def to_player_briefing(self) -> str:
        """Generate a textual briefing for the player."""
        lines = [f"Attack chain with {len(self.nodes)} steps:"]
        for i, mid in enumerate(self.topo_order(), 1):
            mod = self.nodes[mid]
            marker = " 🚩" if mid in self.flag_nodes else ""
            lines.append(f"  Step {i}: {mod.name}{marker}")
        return "\n".join(lines)
