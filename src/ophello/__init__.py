"""Portable 1Password secret resolution, including Windows Hello in WSL.

Applications use :func:`read` / :func:`resolve` rather than invoking ``op``
directly. Reads try the service-account SDK, native ``op read``, the bundled
platform helper, then the WSL Windows CLI fallback. Values are cached only in
this process; the Windows helper also uses a DPAPI-protected cache.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Optional

__all__ = ["clear_cache", "is_available", "read", "resolve"]

logger = logging.getLogger(__name__)
try:
    _PACKAGE_VERSION = version("ophello")
except PackageNotFoundError:
    _PACKAGE_VERSION = "dev"
_CACHE: dict[tuple[str, str], str] = {}


def clear_cache() -> None:
    """Clear cached values after a secret rotation or between isolated runs."""
    _CACHE.clear()


def resolve(value: str, *, account: Optional[str] = None) -> str:
    """Return a literal unchanged, or resolve an ``op://`` reference."""
    text = value.strip()
    if text.startswith("op://"):
        return read(text, account=account)[0]
    return text


def is_available() -> bool:
    """Whether an SDK, 1Password CLI, or bundled helper is available."""
    if os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"):
        return True
    if shutil.which("op") or shutil.which("op.exe") or shutil.which("op-hello"):
        return True
    return _bundled_script().is_file()


def read(*refs: str, account: Optional[str] = None) -> list[str]:
    """Read one to eight references, batch them, and reuse process-cached values.

    ``account`` overrides ``OP_HELLO_ACCOUNT`` / ``OP_ACCOUNT``. Cocli uses
    this to preserve its configured default; standalone apps can omit it.
    """
    cleaned = [ref.strip() for ref in refs if ref and ref.strip()]
    if not cleaned or len(cleaned) > 8:
        raise ValueError(
            "op-hello can read one to eight 1Password references at a time"
        )
    for ref in cleaned:
        if not ref.startswith("op://"):
            raise ValueError("1Password references must start with op://")
    selected_account = (
        account
        or os.environ.get("OP_HELLO_ACCOUNT")
        or os.environ.get("OP_ACCOUNT")
        or ""
    )
    keys = [(selected_account, ref) for ref in cleaned]
    missing_keys = list(dict.fromkeys(key for key in keys if key not in _CACHE))
    if missing_keys:
        missing_refs = [ref for _, ref in missing_keys]
        values = _read_uncached(*missing_refs, account=selected_account or None)
        if len(values) != len(missing_keys):
            raise RuntimeError(
                f"1Password returned {len(values)} value(s); "
                f"expected {len(missing_keys)}."
            )
        for key, value in zip(missing_keys, values):
            if not value:
                raise RuntimeError("1Password returned an empty secret.")
            _CACHE[key] = value
    return [_CACHE[key] for key in keys]


def _bundled_script() -> Path:
    override = os.environ.get("OP_HELLO_BIN", "").strip()
    if override:
        return Path(override)
    package = Path(__file__).resolve().parent
    installed = package / "bin" / "op-hello"
    if installed.is_file():
        return installed
    return Path(__file__).resolve().parents[2] / "bin" / "op-hello"


def _op_env(account: Optional[str] = None) -> dict[str, str]:
    env = os.environ.copy()
    selected = account or env.get("OP_HELLO_ACCOUNT") or env.get("OP_ACCOUNT")
    if account:
        env["OP_HELLO_ACCOUNT"] = account
        env["OP_ACCOUNT"] = account
    elif selected:
        env.setdefault("OP_ACCOUNT", selected)
    return env


def _run(
    argv: list[str],
    timeout: int = 60,
    *,
    cwd: Optional[str] = None,
    account: Optional[str] = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
        env=_op_env(account),
    )


def _read_uncached(*refs: str, account: Optional[str] = None) -> list[str]:
    values = _read_sdk(*refs)
    if values is not None:
        return values
    values, native_error = _read_native_cli(*refs, account=account)
    if values is not None:
        return values
    values, helper_error = _read_bundled_cli(*refs, account=account)
    if values is not None:
        return values
    values, windows_error = _read_windows_cli(*refs, account=account)
    if values is not None:
        return values
    detail = helper_error or windows_error or native_error or "1Password read failed."
    detail = re.sub(r"op://[^\s]+", "the 1Password item", detail)
    raise RuntimeError(detail)


def _read_sdk(*refs: str) -> Optional[list[str]]:
    token = os.environ.get("OP_SERVICE_ACCOUNT_TOKEN")
    if not token:
        return None
    try:
        from onepassword.client import Client  # type: ignore[import-not-found]

        async def resolve_all() -> list[str]:
            client = await Client.authenticate(
                auth=token,
                integration_name=os.environ.get("OP_HELLO_INTEGRATION_NAME", "op-hello"),
                integration_version=os.environ.get(
                    "OP_HELLO_INTEGRATION_VERSION", _PACKAGE_VERSION
                ),
            )
            return [str(await client.secrets.resolve(ref)) for ref in refs]

        return asyncio.run(resolve_all())
    except Exception:
        logger.debug("1Password SDK lookup failed; trying configured CLI readers")
        return None


def _account_args(account: Optional[str]) -> list[str]:
    selected = account or os.environ.get("OP_HELLO_ACCOUNT") or os.environ.get("OP_ACCOUNT")
    return ["--account", selected] if selected else []


def _read_native_cli(*refs: str, account: Optional[str] = None) -> tuple[Optional[list[str]], Optional[str]]:
    binary = shutil.which("op")
    if not binary or binary.lower().endswith(".exe"):
        return None, None
    values: list[str] = []
    for ref in refs:
        try:
            result = _run([binary, "read", ref, *_account_args(account)], timeout=60, account=account)
        except (OSError, subprocess.TimeoutExpired):
            return None, None
        if result.returncode:
            return None, result.stderr.strip() or "1Password CLI read failed."
        values.append(result.stdout.rstrip("\r\n"))
    return values, None


def _read_bundled_cli(*refs: str, account: Optional[str] = None) -> tuple[Optional[list[str]], Optional[str]]:
    script = _bundled_script()
    if not script.is_file():
        return None, None
    bash = shutil.which("bash")
    if not bash:
        return None, "The op-hello platform helper requires Bash."
    timeout = int(os.environ.get("OP_HELLO_TIMEOUT", "120"))
    try:
        result = _run([bash, str(script), "read", *refs], timeout=timeout + 5, account=account)
    except (OSError, subprocess.TimeoutExpired):
        return None, "1Password Windows Hello timed out or the helper could not start."
    if result.returncode:
        return None, result.stderr.strip() or "1Password platform helper failed."
    lines = [line for line in result.stdout.splitlines() if line]
    if len(lines) != len(refs):
        return None, "1Password returned an unexpected number of values."
    return lines, None


def _read_windows_cli(*refs: str, account: Optional[str] = None) -> tuple[Optional[list[str]], Optional[str]]:
    """Last-resort WSL path matching Cocli's Windows op.exe fallback."""
    if not Path("/mnt/c/Program Files/1Password CLI/op.exe").is_file():
        return None, None
    binary = "/mnt/c/Program Files/1Password CLI/op.exe"
    values: list[str] = []
    for ref in refs:
        argv = [binary, "read", ref, *_account_args(account)]
        if Path("/init").is_file():
            argv.insert(0, "/init")
        try:
            result = _run(argv, timeout=60, cwd="/mnt/c/Windows", account=account)
        except (OSError, subprocess.TimeoutExpired):
            return None, "Windows 1Password CLI timed out or could not start."
        if result.returncode:
            return None, result.stderr.strip() or "Windows 1Password CLI read failed."
        values.append(result.stdout.replace("\r", "").strip())
    return values, None
