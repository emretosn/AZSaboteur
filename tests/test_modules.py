"""Tests for the module catalog system."""

from pathlib import Path

from saboteur.modules.base import ModuleCategory, VulnModule
from saboteur.modules.catalog import ModuleCatalog, load_catalog

MODULES_DIR = Path(__file__).resolve().parent.parent / "modules"


def _make_module(id: str, category: str, requires: list[str], provides: list[str]) -> VulnModule:
    return VulnModule(
        id=id,
        name=f"Test {id}",
        category=ModuleCategory(category),
        requires=requires,
        provides=provides,
    )


class TestVulnModule:
    def test_is_entry_point(self):
        mod = _make_module("TEST-1", "web", ["network_access"], ["token"])
        assert mod.is_entry_point is True

    def test_not_entry_point(self):
        mod = _make_module("TEST-2", "storage", ["token"], ["secret"])
        assert mod.is_entry_point is False

    def test_can_follow(self):
        a = _make_module("A", "web", ["network_access"], ["managed_identity_token"])
        b = _make_module("B", "storage", ["managed_identity_token"], ["keyvault_secret"])
        assert b.can_follow(a) is True
        assert a.can_follow(b) is False

    def test_to_dict_roundtrip(self):
        mod = _make_module("RT-1", "compute", ["vm_shell"], ["token"])
        data = mod.to_dict()
        restored = VulnModule.from_dict(data)
        assert restored.id == mod.id
        assert restored.category == mod.category
        assert restored.requires == mod.requires
        assert restored.provides == mod.provides


class TestModuleCatalog:
    def test_register_and_get(self):
        catalog = ModuleCatalog()
        mod = _make_module("X", "web", ["network_access"], ["token"])
        catalog.register(mod)
        assert catalog.get("X") is mod
        assert len(catalog) == 1
        assert "X" in catalog

    def test_filter_by_category(self):
        catalog = ModuleCatalog()
        catalog.register(_make_module("W1", "web", ["network_access"], ["token"]))
        catalog.register(_make_module("S1", "storage", ["token"], ["secret"]))
        web_only = catalog.filter(categories=[ModuleCategory.WEB])
        assert len(web_only) == 1
        assert web_only[0].id == "W1"

    def test_entry_points(self):
        catalog = ModuleCatalog()
        catalog.register(_make_module("E1", "web", ["network_access"], ["token"]))
        catalog.register(_make_module("E2", "storage", ["token"], ["secret"]))
        entries = catalog.entry_points()
        assert len(entries) == 1
        assert entries[0].id == "E1"

    def test_followers(self):
        catalog = ModuleCatalog()
        a = _make_module("A", "web", ["network_access"], ["managed_identity_token"])
        b = _make_module("B", "storage", ["managed_identity_token"], ["keyvault_secret"])
        c = _make_module("C", "compute", ["vm_shell"], ["token"])
        catalog.register(a)
        catalog.register(b)
        catalog.register(c)
        followers = catalog.followers(a)
        assert len(followers) == 1
        assert followers[0].id == "B"

    def test_load_yaml(self):
        catalog = load_catalog(MODULES_DIR)
        assert len(catalog) > 0
        assert "WEB-SSRF" in catalog
        assert "STR-KEYVAULT-POLICY" in catalog
        ssrf = catalog.get("WEB-SSRF")
        assert ssrf is not None
        assert ssrf.is_entry_point is True
