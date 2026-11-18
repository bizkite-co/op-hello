# op-hello

Read a 1Password secret so the desktop app can raise Windows Hello. Store
`op://Vault/Item/field` in the environment. Resolve it when the program starts.

```bash
export API_TOKEN=op://Private/Service/credential
op-hello resolve "$API_TOKEN"
```

Install the published package, or use this checkout for local development:

```bash
uv add ophello
uv add --editable ../op-hello
```

Install the optional SDK extra to use service-account authentication:

```bash
uv add "ophello[sdk]"
```

The public Python API is suitable for application adapters and plugins. It
tries `OP_SERVICE_ACCOUNT_TOKEN` with the optional 1Password SDK, then native
`op read`, then the bundled platform helper and WSL Windows CLI fallback. A
process-local cache avoids repeating reads; Windows also keeps a
DPAPI-protected cache for the configured TTL. `clear_cache()` clears the current
process cache; the Windows cache expires according to `OP_HELLO_CACHE_TTL`.
`OP_HELLO_ACCOUNT` or the existing `OP_ACCOUNT` selects an account.

Python projects that already use this checkout:

```python
import os

from ophello import clear_cache, read, resolve

token = resolve(os.environ["API_TOKEN"])
```

Two fields:

```bash
op-hello read op://Private/Service/client-id op://Private/Service/password
```

Stdout is one secret per line and nothing else.

## Why this exists

1Password's secret-reference docs stop at `op read`. These are the parts that
take the time:

1. Turn on **Settings → Developer → Integrate with 1Password CLI** in the desktop app.
2. From WSL, call Windows `op.exe` (`C:\Program Files\1Password CLI\op.exe`). A Linux `op` session does not raise Windows Hello.
3. Start that process with its working directory on `C:\Windows`. `cmd.exe` exits when the working directory is a WSL UNC path.
4. If AutoHotkey is running, suspend it for the read. Its keyboard hook hides the Hello prompt. `windows/ahk-pause.ps1` does that, and it is skipped when AutoHotkey is not installed.
5. Use `op read`. `op item get` returns an OTP seed instead of the current code.
6. Cache the value for 15 minutes with DPAPI, for the current Windows user, in `%LOCALAPPDATA%\op-hello\`. The first read of a field can still prompt. A repeat within 15 minutes does not. Set `OP_HELLO_CACHE_TTL` to the number of minutes.
7. A router or DNS failure looks like `RequestDelegatedSession`. That is the network. The error text says so, and it does not include the secret or the `op://` reference.

## Layout

| Piece | Role |
|---|---|
| `bin/op-hello` | The program other languages call |
| `windows/op-read.ps1` | Windows Hello, DPAPI cache, optional AutoHotkey pause |
| `src/ophello/` | `resolve()` and `read()` for Python |

PowerShell is the Windows implementation because Hello, DPAPI, and AutoHotkey are Windows APIs. A Go or Rust binary would still shell out to `op.exe` and reimplement those calls. On macOS and Linux, `op-hello` calls `op read` and the system biometric prompt is the 1Password app's own. The installed CLI and Python library share this same platform helper.

## Use it from another language

Put `bin` on `PATH` and run `op-hello read`. Exit 0 and one line per secret means success. Anything else is on stderr.

The installed `op-hello` command and Python library both use the same platform helper. `OP_HELLO_BIN` overrides the helper path for deployments that provide their own adapter.

## Limits

One command accepts up to eight references. The desktop app has to be unlocked, and someone has to be present for the first prompt. The call fails after `OP_HELLO_TIMEOUT` seconds (default 120) if nobody approves it.


## Release

Use the local `verkit` CLI at `~/repos/verkit` to manage the semantic version:

```bash
uv run --project ~/repos/verkit verkit inspect
uv run --project ~/repos/verkit verkit promote patch --no-amend
uv run --project ~/repos/verkit verkit tag --no-push
uv build
uv publish
```

`verkit promote` and `verkit tag` commit the version bump and create a matching
local tag; neither uploads artifacts to PyPI. When an `origin` remote is
configured, use `verkit release patch` instead. Configure PyPI trusted publishing or provide credentials
through `uv publish`'s supported environment mechanism; never save tokens in
this repository. Verify the published version and install it from PyPI after
upload.
