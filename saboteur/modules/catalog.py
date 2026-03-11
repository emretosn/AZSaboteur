"""Module catalog — registry, loading, and filtering."""

from __future__ import annotations

from pathlib import Path

import yaml

from saboteur.modules.base import ModuleCategory, VulnModule

CATALOG_DIR = Path(__file__).resolve().parent.parent.parent / "modules"


class ModuleCatalog:
    """Registry of all available vulnerability modules."""

    def __init__(self) -> None:
        self._modules: dict[str, VulnModule] = {}

    def register(self, module: VulnModule) -> None:
        self._modules[module.id] = module

    def get(self, module_id: str) -> VulnModule | None:
        return self._modules.get(module_id)

    @property
    def all(self) -> list[VulnModule]:
        return list(self._modules.values())

    def filter(
        self,
        categories: list[ModuleCategory] | None = None,
    ) -> list[VulnModule]:
        """Filter modules by categories."""
        result = self.all
        if categories:
            result = [m for m in result if m.category in categories]
        return result

    def entry_points(
        self,
        categories: list[ModuleCategory] | None = None,
    ) -> list[VulnModule]:
        """Get modules that can serve as chain entry points."""
        return [m for m in self.filter(categories) if m.is_entry_point]

    def followers(self, provider: VulnModule) -> list[VulnModule]:
        """Get modules that can follow the given module in a chain."""
        return [m for m in self.all if m.can_follow(provider) and m.id != provider.id]

    def load_yaml(self, path: Path | None = None) -> None:
        """Load module definitions from YAML files in a directory."""
        catalog_path = path or CATALOG_DIR
        if not catalog_path.is_dir():
            return
        for yaml_file in sorted(catalog_path.glob("*.yaml")):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            if data is None:
                continue
            modules = data if isinstance(data, list) else [data]
            for mod_data in modules:
                self.register(VulnModule.from_dict(mod_data))

    def __len__(self) -> int:
        return len(self._modules)

    def __contains__(self, module_id: str) -> bool:
        return module_id in self._modules


def load_catalog(path: Path | None = None) -> ModuleCatalog:
    """Convenience: create a catalog and load all YAML definitions."""
    catalog = ModuleCatalog()
    catalog.load_yaml(path)
    return catalog
