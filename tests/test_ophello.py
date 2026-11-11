import os
import subprocess
from pathlib import Path

import pytest

from ophello import read, resolve

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "op-hello"


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    import ophello

    ophello._CACHE.clear()


def test_resolve_leaves_literals_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OP_HELLO_BIN", "/does/not/run")
    assert resolve("mailbox-secret") == "mailbox-secret"


def test_read_uses_the_cli_once_and_then_the_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "op-hello"
    fake.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' one\n"
        "printf '%s\\n' two\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    calls = {"n": 0}
    real_run = subprocess.run

    def spy(*args, **kwargs):
        calls["n"] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setenv("OP_HELLO_BIN", str(fake))
    monkeypatch.setattr(subprocess, "run", spy)
    assert read("op://Vault/Item/a", "op://Vault/Item/b") == ["one", "two"]
    assert read("op://Vault/Item/a") == ["one"]
    assert calls["n"] == 1


def test_cli_resolve_prints_a_literal() -> None:
    proc = subprocess.run(
        [str(CLI), "resolve", "literal-value"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert proc.stdout == "literal-value\n"


def test_cli_scrubs_a_failed_reference(tmp_path: Path) -> None:
    delegate = tmp_path / "fail.sh"
    delegate.write_text(
        "#!/bin/sh\n"
        "echo 'RequestDelegatedSession for op://Private/Item/password' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    delegate.chmod(0o755)
    env = os.environ.copy()
    env["OP_HELLO_DELEGATE"] = str(delegate)
    proc = subprocess.run(
        [str(CLI), "read", "op://Private/Item/password"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 1
    assert "op://" not in proc.stderr
    assert "the 1Password item" in proc.stderr
    assert "check the network" in proc.stderr
