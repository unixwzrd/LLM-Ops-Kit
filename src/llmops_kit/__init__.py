"""LLM-Ops-Kit control library."""

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


_SOURCE_PROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
if _SOURCE_PROJECT.is_file():
    __version__ = str(tomllib.loads(_SOURCE_PROJECT.read_text(encoding="utf-8"))["project"]["version"])
else:
    try:
        __version__ = version("llm-ops-kit")
    except PackageNotFoundError:
        __version__ = "source"

__all__ = ["__version__"]
