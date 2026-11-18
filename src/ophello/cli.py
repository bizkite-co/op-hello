"""Installed command-line entry point for op-hello."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _script() -> Path:
    override = os.environ.get("OP_HELLO_BIN", "").strip()
    if override:
        return Path(override)
    package = Path(__file__).resolve().parent
    installed = package / "bin" / "op-hello"
    if installed.is_file():
        return installed
    return Path(__file__).resolve().parents[2] / "bin" / "op-hello"


def main() -> None:
    """Run the platform helper, preserving one-secret-per-line stdout."""
    if os.name == "nt":
        package = Path(__file__).resolve().parent
        ps = shutil.which("powershell.exe") or shutil.which("powershell")
        script = package / "windows" / "op-read.ps1"
        if not ps or not script.is_file():
            print("op-hello: Windows PowerShell helper is unavailable.", file=sys.stderr)
            raise SystemExit(1)
        proc = subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *sys.argv[1:]])
    else:
        bash = shutil.which("bash")
        script = _script()
        if not bash or not script.is_file():
            print("op-hello: bundled Bash helper is unavailable.", file=sys.stderr)
            raise SystemExit(1)
        proc = subprocess.run([bash, str(script), *sys.argv[1:]])
    raise SystemExit(proc.returncode)
