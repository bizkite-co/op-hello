import os
import shutil
import subprocess
from pathlib import Path

import pytest

import op_hello
from op_hello import cli, read, resolve

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "op-hello"


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    op_hello._CACHE.clear()


def test_resolve_leaves_literals_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OP_HELLO_BIN", "/does/not/run")
    assert resolve("mailbox-secret") == "mailbox-secret"


def test_read_uses_the_reader_once_and_then_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_reader(*refs: str, account=None) -> list[str]:
        calls.append(refs)
        return ["one", "two"][:len(refs)]

    monkeypatch.setattr(op_hello, "_read_uncached", fake_reader)
    assert read("op://Vault/Item/a", "op://Vault/Item/b") == ["one", "two"]
    assert read("op://Vault/Item/a") == ["one"]
    assert calls == [("op://Vault/Item/a", "op://Vault/Item/b")]


def test_python_reader_uses_powershell_helper_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(op_hello, "_is_windows", lambda: True)
    monkeypatch.setattr(
        op_hello.shutil,
        "which",
        lambda name: "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
        if name == "powershell.exe"
        else None,
    )
    called = {}

    def fake_run(argv, **kwargs):
        called["argv"] = argv
        called["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0, "one\ntwo\n", "")

    monkeypatch.setattr(op_hello, "_run", fake_run)
    values, error = op_hello._read_bundled_cli(
        "op://Vault/Item/a", "op://Vault/Item/b", account="work"
    )
    assert values == ["one", "two"]
    assert error is None
    assert called["argv"][0].endswith("powershell.exe")
    assert called["argv"][1:5] == ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
    assert called["argv"][5].endswith("windows/op-read.ps1")
    assert called["argv"][6:] == ["op://Vault/Item/a", "op://Vault/Item/b"]
    assert called["kwargs"]["account"] == "work"


def test_windows_cli_resolve_prints_a_literal(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "resolve", lambda value: value)
    cli._windows_main(["resolve", "literal-value"])
    assert capsys.readouterr().out == "literal-value\n"


def test_windows_cli_read_prints_one_value_per_line(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "read", lambda *refs: ["one", "two"])
    cli._windows_main(["read", "op://Vault/Item/a", "op://Vault/Item/b"])
    assert capsys.readouterr().out == "one\ntwo\n"


def test_powershell_helper_parses_when_powershell_is_available() -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell is not installed")
    script = ROOT / "windows" / "op-read.ps1"
    script_path = str(script)
    if os.name != "nt":
        wslpath = shutil.which("wslpath")
        if not wslpath:
            pytest.skip("PowerShell is present but WSL path conversion is unavailable")
        converted = subprocess.run(
            [wslpath, "-w", script_path], capture_output=True, text=True, check=True
        )
        script_path = converted.stdout.strip()
    escaped = script_path.replace("'", "''")
    command = (
        "$tokens=$null; $parseErrors=$null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped}', "
        "[ref]$tokens, [ref]$parseErrors) | Out-Null; "
        "if ($parseErrors.Count -gt 0) { $parseErrors | ForEach-Object { Write-Error $_.Message }; exit 1 }"
    )
    proc = subprocess.run(
        [powershell, "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


@pytest.mark.skipif(os.name == "nt", reason="Exercises the Bash helper")
def test_cli_resolve_prints_a_literal() -> None:
    proc = subprocess.run(
        [str(CLI), "resolve", "literal-value"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert proc.stdout == "literal-value\n"


@pytest.mark.skipif(os.name == "nt", reason="Exercises the Bash helper")
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


def test_version_command_prints_project_version(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import verkit

    monkeypatch.setattr(verkit, "inspect_project", lambda: type("Info", (), {"version": "0.2.3"})())
    assert cli._version_main(["version"]) is True
    assert capsys.readouterr().out == "op-hello 0.2.3\n"


def test_version_release_uses_verkit_and_pushes_by_default(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import verkit

    calls = []
    monkeypatch.setattr(verkit, "release_version", lambda part, **kwargs: (calls.append((part, kwargs)) or ("0.2.4", "v0.2.4")))
    assert cli._version_main(["version", "release", "patch"]) is True
    assert calls == [("patch", {"push": True})]
    assert capsys.readouterr().out == "Released op-hello 0.2.4 (v0.2.4)\n"
