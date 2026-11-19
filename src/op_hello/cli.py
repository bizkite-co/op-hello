"""Installed command-line entry point for op-hello."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import read, resolve


def _script() -> Path:
    override = os.environ.get("OP_HELLO_BIN", "").strip()
    if override:
        return Path(override)
    package = Path(__file__).resolve().parent
    installed = package / "bin" / "op-hello"
    if installed.is_file():
        return installed
    return Path(__file__).resolve().parents[2] / "bin" / "op-hello"


def _usage(stream=None) -> None:
    print(
        "Usage:\n  oph read op://Vault/Item/field [op://Vault/Item/other ...]\n"
        "  oph resolve VALUE\n"
        "  oph version\n"
        "  oph version release <major|minor|patch> [--no-push]",
        file=stream,
    )


def _version_main(argv: list[str]) -> bool:
    """Handle project version and Verkit release commands."""
    if not argv or argv[0] != "version":
        return False
    from verkit import inspect_project, release_version

    if argv[1:] in ([], ["--help"], ["-h"]):
        print(f"op-hello {inspect_project().version}")
        return True
    if len(argv) in (3, 4) and argv[1] == "release" and argv[2] in {
        "major", "minor", "patch"
    } and (len(argv) == 3 or argv[3] == "--no-push"):
        new_version, tag = release_version(argv[2], push=len(argv) == 3)
        print(f"Released op-hello {new_version} ({tag})")
        return True
    _usage(sys.stderr)
    raise SystemExit(2)


def _windows_main(argv: list[str]) -> None:
    """Run the Windows CLI through the shared Python API and PowerShell helper."""
    if argv in (["-h"], ["--help"]):
        _usage()
        return
    if not argv:
        _usage(sys.stderr)
        raise SystemExit(2)
    try:
        if argv[0] == "read":
            values = read(*argv[1:])
        elif argv[0] == "resolve" and len(argv) == 2:
            values = [resolve(argv[1])]
        else:
            _usage(sys.stderr)
            raise SystemExit(2)
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"op-hello: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    for value in values:
        print(value)


def main() -> None:
    """Run the platform CLI, preserving one-secret-per-line stdout."""
    if _version_main(sys.argv[1:]):
        return
    if os.name == "nt":
        _windows_main(sys.argv[1:])
        return
    bash = shutil.which("bash")
    script = _script()
    if not bash or not script.is_file():
        print("op-hello: bundled Bash helper is unavailable.", file=sys.stderr)
        raise SystemExit(1)
    proc = subprocess.run([bash, str(script), *sys.argv[1:]])
    raise SystemExit(proc.returncode)
