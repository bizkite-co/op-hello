"""Import wrapper around the `op-hello` command.

The command is the program. This module caches values for the life of the
process and returns a literal unchanged when it does not start with ``op://``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

__all__ = ["read", "resolve"]

_CACHE: dict[str, str] = {}


def resolve(value: str) -> str:
    """Return a literal, or the secret behind an ``op://`` reference."""
    text = value.strip()
    if text.startswith("op://"):
        return read(text)[0]
    return text


def read(*refs: str) -> list[str]:
    """Read one to eight ``op://`` refs. One Windows Hello covers a repeat read."""
    cleaned = [ref.strip() for ref in refs if ref and ref.strip()]
    if not cleaned or len(cleaned) > 8:
        raise ValueError("op-hello can read one to eight 1Password references at a time")
    for ref in cleaned:
        if not ref.startswith("op://"):
            raise ValueError("1Password references must start with op://")

    missing = [ref for ref in cleaned if ref not in _CACHE]
    if missing:
        for ref, value in zip(missing, _read_uncached(*missing), strict=True):
            _CACHE[ref] = value
    return [_CACHE[ref] for ref in cleaned]


def _executable() -> str:
    override = os.environ.get("OP_HELLO_BIN", "").strip()
    if override:
        return override
    found = shutil.which("op-hello")
    if found:
        return found
    candidate = Path(__file__).resolve().parents[2] / "bin" / "op-hello"
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError("op-hello is not on PATH. Add the repo's bin directory to PATH.")


def _read_uncached(*refs: str) -> list[str]:
    timeout = int(os.environ.get("OP_HELLO_TIMEOUT", "120"))
    try:
        proc = subprocess.run(
            [_executable(), "read", *refs],
            capture_output=True,
            text=True,
            timeout=timeout + 5,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "1Password Windows Hello timed out. Approve the popup; this fails if you are away."
        ) from exc
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"exit {proc.returncode}"
        raise RuntimeError(detail)
    lines = [line for line in proc.stdout.splitlines() if line]
    if len(lines) < len(refs):
        raise RuntimeError(f"1Password returned {len(lines)} value(s); expected {len(refs)}.")
    return lines[: len(refs)]
