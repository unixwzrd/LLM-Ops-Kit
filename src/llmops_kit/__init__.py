"""LLM-Ops-Kit control library."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("llm-ops-kit")
except PackageNotFoundError:  # Source checkout.
    __version__ = "0.9.0b1"

__all__ = ["__version__"]
