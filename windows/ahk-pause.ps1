# Suspend or resume AutoHotkey. Its keyboard hook steals the Windows Hello prompt.
# Usage: ahk-pause.ps1 -Suspend | -Resume

param(
    [switch]$Suspend,
    [switch]$Resume
)

if (-not $Suspend -and -not $Resume) {
    Write-Error "Specify -Suspend or -Resume"
    exit 1
}

$signature = @'
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;

public static class AhkProc {
    [DllImport("ntdll.dll")]
    public static extern int NtSuspendProcess(IntPtr processHandle);

    [DllImport("ntdll.dll")]
    public static extern int NtResumeProcess(IntPtr processHandle);

    public static void SuspendPid(int pid) {
        using (var p = Process.GetProcessById(pid)) {
            NtSuspendProcess(p.Handle);
        }
    }

    public static void ResumePid(int pid) {
        using (var p = Process.GetProcessById(pid)) {
            NtResumeProcess(p.Handle);
        }
    }
}
'@

try {
    Add-Type -TypeDefinition $signature -ErrorAction Stop | Out-Null
} catch {
    # The type is already loaded in this process.
}

$procs = @(Get-Process -Name "AutoHotkey*" -ErrorAction SilentlyContinue)
if ($procs.Count -eq 0) {
    exit 0
}

foreach ($p in $procs) {
    try {
        if ($Suspend) {
            [AhkProc]::SuspendPid($p.Id)
        } else {
            [AhkProc]::ResumePid($p.Id)
        }
    } catch {
        # The process exited between the list and the call.
    }
}
