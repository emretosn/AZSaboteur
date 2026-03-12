"""Base vulnerability module definition."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModuleCategory(str, Enum):
    WEB = "web"
    IDENTITY = "identity"
    COMPUTE = "compute"
    STORAGE = "storage"
    NETWORKING = "networking"


@dataclass
class VulnModule:
    """A single vulnerability building block that can be composed into attack chains."""

    id: str
    name: str
    category: ModuleCategory
    requires: list[str]
    provides: list[str]
    description: str = ""
    terraform_module: str = ""
    ansible_role: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def is_entry_point(self) -> bool:
        """Entry points only require network_access."""
        return self.requires == ["network_access"]

    def can_follow(self, other: VulnModule) -> bool:
        """Check if this module can follow another in a chain."""
        return any(req in other.provides for req in self.requires)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "requires": self.requires,
            "provides": self.provides,
            "description": self.description,
            "terraform_module": self.terraform_module,
            "ansible_role": self.ansible_role,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VulnModule:
        return cls(
            id=data["id"],
            name=data["name"],
            category=ModuleCategory(data["category"]),
            requires=data["requires"],
            provides=data["provides"],
            description=data.get("description", ""),
            terraform_module=data.get("terraform_module", ""),
            ansible_role=data.get("ansible_role", ""),
            tags=data.get("tags", []),
        )
