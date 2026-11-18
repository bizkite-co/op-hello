# Read one or more op:// secrets with Windows op.exe.
# AutoHotkey is suspended when ahk-pause.ps1 sits next to this script.
# A successful read is cached for this Windows user with DPAPI.
#
# Usage:
#   op-read.ps1 "op://Vault/Item/field" ["op://Vault/Item/other" ...]
# One secret per line on stdout. Nothing else.

param(
    [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
    [string[]]$Refs
)

$ErrorActionPreference = "Stop"
$MaxRefs = 8

if ($Refs.Count -gt $MaxRefs) {
    Write-Error "op-read accepts at most $MaxRefs references"
    exit 1
}
foreach ($ref in $Refs) {
    if (-not $ref.StartsWith("op://")) {
        Write-Error "1Password references must start with op://"
        exit 1
    }
}

$op = $env:OP_EXE
if (-not $op) {
    $op = "C:\Program Files\1Password CLI\op.exe"
}
if (-not (Test-Path $op)) {
    $found = Get-Command op.exe -ErrorAction SilentlyContinue
    if ($found) { $op = $found.Source }
}
if (-not (Test-Path $op)) {
    Write-Error "op.exe not found. Install the 1Password CLI and turn on developer integration."
    exit 1
}

$pause = if ($env:OP_AHK_PAUSE) { $env:OP_AHK_PAUSE } else { Join-Path $PSScriptRoot "ahk-pause.ps1" }
$cacheMinutes = 15
if ($env:OP_HELLO_CACHE_TTL) {
    $cacheMinutes = [int]$env:OP_HELLO_CACHE_TTL
}
$cachePath = Join-Path $env:LOCALAPPDATA "op-hello\op-read-cache.json"
$cacheTtl = [TimeSpan]::FromMinutes($cacheMinutes)

function Get-RefKey([string]$Ref) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Ref)
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "")
    } finally {
        $sha.Dispose()
    }
}

function Read-Cache {
    if (-not (Test-Path $cachePath)) { return @{} }
    try {
        $raw = Get-Content -Raw -Path $cachePath | ConvertFrom-Json
        $map = @{}
        if ($raw) {
            foreach ($prop in $raw.PSObject.Properties) { $map[$prop.Name] = $prop.Value }
        }
        return $map
    } catch {
        return @{}
    }
}

function Get-Cached([string]$Ref) {
    $cache = Read-Cache
    $account = if ($env:OP_HELLO_ACCOUNT) { $env:OP_HELLO_ACCOUNT } else { $env:OP_ACCOUNT }
    $key = Get-RefKey "$account`n$Ref"
    if (-not $cache.ContainsKey($key)) { return $null }
    $entry = $cache[$key]
    if ([int64]$entry.exp -lt [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) { return $null }
    Add-Type -AssemblyName System.Security
    $protected = [Convert]::FromBase64String([string]$entry.blob)
    $clear = [Security.Cryptography.ProtectedData]::Unprotect(
        $protected, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
    return [Text.Encoding]::UTF8.GetString($clear)
}

function Set-Cached([string]$Ref, [string]$Value) {
    Add-Type -AssemblyName System.Security
    $dir = Split-Path $cachePath
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    $protected = [Security.Cryptography.ProtectedData]::Protect(
        [Text.Encoding]::UTF8.GetBytes($Value),
        $null,
        [Security.Cryptography.DataProtectionScope]::CurrentUser)
    $cache = Read-Cache
    $account = if ($env:OP_HELLO_ACCOUNT) { $env:OP_HELLO_ACCOUNT } else { $env:OP_ACCOUNT }
    $cache[(Get-RefKey "$account`n$Ref")] = [pscustomobject]@{
        exp = [DateTimeOffset]::UtcNow.Add($cacheTtl).ToUnixTimeSeconds()
        blob = [Convert]::ToBase64String($protected)
    }
    $cache | ConvertTo-Json | Set-Content -Path $cachePath -Encoding UTF8
}

function Invoke-OpRead([string]$Ref) {
    $cached = Get-Cached $Ref
    if ($cached) { return $cached }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $op
    $account = if ($env:OP_HELLO_ACCOUNT) { $env:OP_HELLO_ACCOUNT } else { $env:OP_ACCOUNT }
    if ($account) {
        $psi.Arguments = "read `"$Ref`" --account `"$account`""
    } else {
        $psi.Arguments = "read `"$Ref`""
    }
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    $stdout = $p.StandardOutput.ReadToEnd()
    $stderr = $p.StandardError.ReadToEnd()
    $p.WaitForExit()
    if ($p.ExitCode -ne 0) {
        if ($stderr) { [Console]::Error.WriteLine($stderr.TrimEnd()) }
        throw "op read failed (exit $($p.ExitCode))"
    }
    $value = ($stdout -replace "[\r\n]+", "").Trim()
    if ($value) { Set-Cached $Ref $value }
    return $value
}

$paused = $false
try {
    if (Test-Path $pause) {
        & $pause -Suspend 2>$null
        $paused = $true
    }
    $values = @()
    foreach ($ref in $Refs) {
        $values += (Invoke-OpRead $ref)
    }
    if ($values -contains "" -or $values -contains $null) {
        throw "Empty secret from 1Password"
    }
    foreach ($value in $values) {
        Write-Output $value
    }
} finally {
    if ($paused) {
        & $pause -Resume 2>$null
    }
}
