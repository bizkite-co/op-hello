# op-hello

Read a 1Password secret so the desktop app can raise Windows Hello. Store
`op://Vault/Item/field` in the environment. Resolve it when the program starts.

```bash
export API_TOKEN=op://Private/Service/credential
op-hello resolve "$API_TOKEN"
```

Python projects that already use this checkout:

```python
from ophello import resolve

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

PowerShell is the Windows implementation because Hello, DPAPI, and AutoHotkey are Windows APIs. A Go or Rust binary would still shell out to `op.exe` and reimplement those calls. On macOS and Linux, `bin/op-hello` calls `op read` and the system biometric prompt is the 1Password app's own. Python is only the import for a Python app.

## Use it from another language

Put `bin` on `PATH` and run `op-hello read`. Exit 0 and one line per secret means success. Anything else is on stderr.

An editable Python install from this repo finds `bin/op-hello` next to `src/`. `OP_HELLO_BIN` overrides that path.

```bash
uv add --editable ../op-hello
```

## Limits

One command accepts up to eight references. The desktop app has to be unlocked, and someone has to be present for the first prompt. The call fails after `OP_HELLO_TIMEOUT` seconds (default 120) if nobody approves it.
