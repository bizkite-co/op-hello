# op-hello agent guide

## Purpose

`op-hello` is a portable Python library and CLI for reading 1Password `op://`
references. Applications should use `ophello.read`, `ophello.resolve`, and
`ophello.clear_cache`; do not duplicate its platform/authentication logic.

## Architecture and behavior

- Reader order: optional 1Password service-account SDK, native `op` CLI, the
  packaged platform helper, then the WSL `op.exe` fallback.
- Linux/macOS use the shell helper and the native 1Password CLI. Windows uses
  PowerShell, Windows Hello integration, and DPAPI-protected disk caching.
- The process cache is keyed by account and reference. `read()` accepts one to
  eight references; `resolve()` leaves literal values unchanged.
- `OP_HELLO_ACCOUNT` takes precedence over `OP_ACCOUNT`; the `account=` API
  argument takes precedence over both.
- Secret values belong only on successful stdout/API return values. Never log,
  print in diagnostics, commit, or place them in examples. Scrub `op://`
  references from failure messages.
- The SDK is optional. Keep CLI/helper fallbacks available when it is absent or
  service-account authentication fails.

## Packaging and platform files

- The installable package is `src/ophello`; the `op-hello` console command is
  declared by `[project.scripts]` and delegates to the packaged helper.
- `pyproject.toml` force-includes `bin/op-hello` and Windows PowerShell helpers
  in the wheel. Preserve those paths when changing package layout.
- Keep account selection and caching behavior consistent across Python, Bash,
  PowerShell, and WSL paths.

## Development and release

- Inspect version state with `verkit inspect` and conventions with
  `verkit conventions` (the local source is `~/repos/verkit`).
- For a patch/minor/major release, use `verkit release <part>` when an origin
  remote is configured. It bumps the project version, commits, tags, and pushes;
  it does **not** upload to PyPI.
- Without an origin remote, use `verkit promote <part> --no-amend`, then
  `verkit tag --no-push`. This avoids amending the source commit. Build and
  publish with `uv build` and `uv publish`. Configure PyPI trusted publishing
  or supply a token through the supported environment/credential mechanism;
  never put a token in command text, source, or logs.
- Before publishing, inspect the wheel and sdist to confirm both CLI helpers
  are included. After upload, verify the release page and install the exact
  version into a clean environment.
- Use the project's configured Python minimum and keep user-facing docs,
  package metadata, CLI help, and agent guidance in sync.
