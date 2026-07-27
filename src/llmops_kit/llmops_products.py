#!/usr/bin/env python
"""Product release inventory used by component status reporting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional


UPDATE_STATES = {"current", "available", "held", "review", "unknown"}


class ProductInventoryError(ValueError):
    """Raised when a product inventory is malformed."""


@dataclass(frozen=True)
class ProductRelease:
    """One installed product and its known upstream release state."""

    product_id: str
    installed_version: str = ""
    latest_version: str = ""
    update_state: str = "unknown"
    source: str = ""
    last_verified: str = ""
    last_updated: str = ""
    decision: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "product_id": self.product_id,
            "installed_version": self.installed_version,
            "latest_version": self.latest_version,
            "update_state": self.update_state,
            "source": self.source,
            "last_verified": self.last_verified,
            "last_updated": self.last_updated,
            "decision": self.decision,
        }


@dataclass(frozen=True)
class ProductInventory:
    """Validated product releases and component bindings."""

    products: Mapping[str, ProductRelease]
    components: Mapping[str, str]

    @classmethod
    def empty(cls) -> "ProductInventory":
        return cls(products={}, components={})

    @classmethod
    def load(cls, path: Path) -> "ProductInventory":
        if not path.is_file():
            return cls.empty()
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProductInventoryError(f"invalid product inventory {path}: {exc}") from exc
        if not isinstance(document, dict) or document.get("schema_version") != 1:
            raise ProductInventoryError(f"{path}: product inventory schema_version must be 1")
        raw_products = document.get("products", {})
        raw_components = document.get("components", {})
        if not isinstance(raw_products, dict) or not isinstance(raw_components, dict):
            raise ProductInventoryError(f"{path}: products and components must be objects")
        products: dict[str, ProductRelease] = {}
        for product_id, raw in raw_products.items():
            if not isinstance(product_id, str) or not product_id or not isinstance(raw, dict):
                raise ProductInventoryError(f"{path}: invalid product entry {product_id!r}")
            update_state = str(raw.get("update_state", "unknown"))
            if update_state not in UPDATE_STATES:
                raise ProductInventoryError(
                    f"{path}: {product_id}.update_state must be one of {sorted(UPDATE_STATES)}"
                )
            values = {
                key: str(raw.get(key, ""))
                for key in (
                    "installed_version",
                    "latest_version",
                    "source",
                    "last_verified",
                    "last_updated",
                    "decision",
                )
            }
            products[product_id] = ProductRelease(
                product_id=product_id,
                update_state=update_state,
                **values,
            )
        components: dict[str, str] = {}
        for component, product_id in raw_components.items():
            if not isinstance(component, str) or not isinstance(product_id, str):
                raise ProductInventoryError(f"{path}: component bindings must be strings")
            if product_id not in products:
                raise ProductInventoryError(
                    f"{path}: component {component!r} references unknown product {product_id!r}"
                )
            components[component] = product_id
        return cls(products=products, components=components)

    def resolve(self, component: Any, profile: Mapping[str, Any]) -> Optional[ProductRelease]:
        product_id = self.components.get(component.qualified_id)
        if not product_id:
            configured = profile.get("product_id", "")
            product_id = str(configured) if isinstance(configured, str) else ""
        return self.products.get(product_id) if product_id else None
