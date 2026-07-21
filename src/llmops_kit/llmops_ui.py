"""Local Textual preferences independent of reconciled desired state."""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class UiPreferences:
    """Validated host-local TUI preferences."""

    auto_refresh: bool = True
    refresh_seconds: int = 15
    theme: str = "high-contrast-dark"

    def as_dict(self) -> dict[str, Any]:
        """Return a stable JSON representation."""

        return asdict(self)


def resolve_ui_path(env: Optional[dict[str, str]] = None) -> Path:
    """Resolve local UI preferences independently of deployed config revisions."""

    values = dict(os.environ if env is None else env)
    if values.get("LLMOPS_UI_CONFIG"):
        return Path(values["LLMOPS_UI_CONFIG"]).expanduser()
    base = Path(values.get("XDG_CONFIG_HOME", Path(values.get("HOME", "~")).expanduser() / ".config"))
    return base.expanduser() / "llm-ops" / "ui.json"


def load_ui_preferences(path: Path) -> UiPreferences:
    """Load local preferences, using defaults when absent."""

    if not path.is_file():
        return UiPreferences()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid UI preferences {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"invalid UI preferences {path}: expected an object")
    auto_refresh = data.get("auto_refresh", True)
    refresh_seconds = data.get("refresh_seconds", 15)
    theme = data.get("theme", "high-contrast-dark")
    if not isinstance(auto_refresh, bool):
        raise ValueError("ui.auto_refresh must be boolean")
    if not isinstance(refresh_seconds, int) or refresh_seconds < 2:
        raise ValueError("ui.refresh_seconds must be an integer of at least 2")
    if theme not in {"high-contrast-dark"}:
        raise ValueError(f"unsupported ui.theme: {theme}")
    return UiPreferences(auto_refresh, refresh_seconds, theme)


def save_ui_preferences(path: Path, preferences: UiPreferences) -> Path:
    """Transactionally save local preferences and preserve the prior file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(f"{path.name}.backup-{time.strftime('%Y%m%dT%H%M%S')}")
    if path.exists():
        shutil.copy2(path, backup)
    temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
    temporary.write_text(
        json.dumps(preferences.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return backup
