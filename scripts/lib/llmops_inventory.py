#!/usr/bin/env python3
"""Inventory loading and host selection for LLM-Ops-Kit."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


SUPPORTED_ROLES = {"admin", "llm", "agent", "hybrid"}
SUPPORTED_TRANSPORTS = {"ssh", "local"}


class InventoryError(ValueError):
    """Raised when an inventory document is invalid."""


@dataclass(frozen=True)
class HostRecord:
    """One managed host and its transport settings."""

    name: str
    role: str
    host: str
    user: str
    port: int
    install_root: str
    public_bin_dir: str
    config_profile: str
    ssh_key: str
    proxy_jump: Optional[str]
    tags: tuple[str, ...]
    transport: str = "ssh"
    control_host: str = ""
    trusted_control: bool = False
    peer_observable: bool = True

    @property
    def destination(self) -> str:
        """Return the SSH destination for this host."""

        return f"{self.user}@{self.host}"

    @property
    def ssh_key_path(self) -> Optional[Path]:
        """Return the expanded SSH key path when one is configured."""

        return Path(self.ssh_key).expanduser() if self.ssh_key else None

    def ssh_base(self) -> list[str]:
        """Return the noninteractive SSH command prefix for this host."""

        command = [
            "ssh",
            "-p",
            str(self.port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]
        if self.ssh_key_path is not None:
            command.extend(["-i", str(self.ssh_key_path)])
        if self.proxy_jump:
            command.extend(["-o", f"ProxyJump={self.proxy_jump}"])
        command.append(self.destination)
        return command

    def control_ssh_base(self) -> list[str]:
        """Return SSH arguments suitable for commands issued by peer control hosts."""

        destination = f"{self.user}@{self.control_host or self.host}"
        command = [
            "ssh",
            "-p",
            str(self.port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]
        command.append(destination)
        return command


def _require_string(data: dict[str, Any], key: str, *, host_name: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InventoryError(f"host {host_name} missing required string: {key}")
    return value


def load_inventory(path: Path) -> dict[str, HostRecord]:
    """Load and validate a canonical JSON inventory."""

    if not path.is_file():
        raise InventoryError(f"inventory not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InventoryError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise InventoryError(f"{path}: top-level inventory must be an object")
    if raw.get("schema_version", 1) != 1:
        raise InventoryError(f"{path}: unsupported schema_version: {raw.get('schema_version')}")
    defaults = raw.get("defaults", {})
    if not isinstance(defaults, dict):
        raise InventoryError(f"{path}: defaults must be an object")
    items = raw.get("hosts")
    if not isinstance(items, list) or not items:
        raise InventoryError(f"{path}: inventory contains no hosts")

    hosts: dict[str, HostRecord] = {}
    for item in items:
        if not isinstance(item, dict):
            raise InventoryError(f"{path}: every host must be an object")
        merged = {**defaults, **item}
        name = _require_string(merged, "name", host_name="<unknown>")
        if name in hosts:
            raise InventoryError(f"duplicate host name: {name}")
        role = _require_string(merged, "role", host_name=name)
        if role not in SUPPORTED_ROLES:
            raise InventoryError(f"host {name} has unsupported role: {role}")
        transport = str(merged.get("transport", "ssh"))
        if transport not in SUPPORTED_TRANSPORTS:
            raise InventoryError(f"host {name} has unsupported transport: {transport}")
        tags = merged.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise InventoryError(f"host {name} tags must be strings")
        trusted_control = merged.get("trusted_control", False)
        if not isinstance(trusted_control, bool):
            raise InventoryError(f"host {name} trusted_control must be a boolean")
        peer_observable = merged.get("peer_observable", True)
        if not isinstance(peer_observable, bool):
            raise InventoryError(f"host {name} peer_observable must be a boolean")
        try:
            port = int(merged.get("port", 22))
        except (TypeError, ValueError) as exc:
            raise InventoryError(f"host {name} port must be an integer") from exc
        hosts[name] = HostRecord(
            name=name,
            role=role,
            host=_require_string(merged, "host", host_name=name),
            user=_require_string(merged, "user", host_name=name),
            port=port,
            install_root=_require_string(merged, "install_root", host_name=name),
            public_bin_dir=str(merged.get("public_bin_dir", "~/.local/bin")),
            config_profile=str(merged.get("config_profile", "default")),
            ssh_key=str(merged.get("ssh_key", "")),
            proxy_jump=str(merged["proxy_jump"]) if merged.get("proxy_jump") else None,
            tags=tuple(tags),
            transport=transport,
            control_host=str(merged.get("control_host", merged["host"])),
            trusted_control=trusted_control,
            peer_observable=peer_observable,
        )
    return hosts


def select_hosts(
    hosts: dict[str, HostRecord],
    *,
    names: Optional[Iterable[str]] = None,
    role: Optional[str] = None,
    tags: Optional[Iterable[str]] = None,
) -> dict[str, HostRecord]:
    """Select hosts by name, role, and tag."""

    selected = dict(hosts)
    if names:
        wanted = set(names)
        selected = {name: host for name, host in selected.items() if name in wanted}
    if role:
        selected = {name: host for name, host in selected.items() if host.role == role}
    if tags:
        wanted_tags = set(tags)
        selected = {
            name: host for name, host in selected.items() if wanted_tags.intersection(host.tags)
        }
    if not selected:
        raise InventoryError("host selection matched no inventory entries")
    return selected
