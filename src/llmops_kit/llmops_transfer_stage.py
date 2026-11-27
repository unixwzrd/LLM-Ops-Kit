"""Private, per-attempt staging for artifacts transferred over SSH."""

from __future__ import annotations

import logging
import shlex
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Iterator, Literal
from uuid import uuid4

log = logging.getLogger(__name__)
RemoteCommand = Callable[[str, int], subprocess.CompletedProcess[str]]


class TransferStageError(RuntimeError):
    """Raised when private transfer staging cannot be created."""


@dataclass(frozen=True)
class TransferStage:
    """An attempt-specific directory that is not an installed revision."""

    kind: Literal["updates", "config"]
    nonce: str = field(default_factory=lambda: uuid4().hex, init=False)

    @property
    def relative(self) -> str:
        return f".cache/llm-ops/{self.kind}/transfer-{self.nonce}"

    def file_expression(self, name: str) -> str:
        """Quote a filename within the stage, leaving the remote HOME expandable."""

        return '"$HOME"/' + shlex.quote(f"{self.relative}/{name}")

    def _setup(self) -> str:
        return (
            "set -e; umask 077; "
            f'base="$HOME/.cache/llm-ops/{self.kind}"; '
            'for p in "$HOME/.cache" "$HOME/.cache/llm-ops" "$base"; do test ! -L "$p"; done; '
            f'transfer="$HOME/{self.relative}"; '
        )

    def create_command(self) -> str:
        """Create a fresh private stage; never reuse an earlier transfer."""

        return self._setup() + 'mkdir -p "$base"; mkdir "$transfer"'

    @staticmethod
    def _lease() -> str:
        # Keep the lease beside the stage so recursive removal cannot drop
        # the lease while the stage is still present.
        return (
            'mkdir "$transfer.in-use"; '
            """trap 'rmdir "$transfer.in-use" || :' 0; """
            'test -d "$transfer"; test ! -L "$transfer"; '
        )

    def use_command(self, command: str) -> str:
        """Hold a lease while a remote process can still be reading the archive."""

        return self._setup() + self._lease() + command

    def cleanup_command(self) -> str:
        """Remove only this stage, refusing to race a still-running apply."""

        return self._setup() + (
            'if test ! -e "$transfer" && test ! -L "$transfer"; then exit 0; fi; '
        ) + self._lease() + 'rm -rf "$transfer"'


@contextmanager
def transfer_stage(
    kind: Literal["updates", "config"], *, run: RemoteCommand, host: str, timeout: int
) -> Iterator[TransferStage]:
    """Cleanup on completion or failure without masking the operation result."""

    stage = TransferStage(kind)
    created = run(stage.create_command(), timeout)
    if created.returncode:
        raise TransferStageError(f"could not create private {kind} transfer stage on {host}")
    try:
        yield stage
    finally:
        try:
            cleaned = run(stage.cleanup_command(), min(timeout, 15))
            if cleaned.returncode:
                log.warning("%s: transfer cleanup deferred; check ~/%s", host, stage.relative)
        except (OSError, subprocess.SubprocessError, RuntimeError):
            log.warning("%s: transfer cleanup could not be verified; check ~/%s", host, stage.relative)
