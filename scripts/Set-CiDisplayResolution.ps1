param(
    [int]$MinimumWidth = 1920,
    [int]$MinimumHeight = 1080,
    [string]$EvidencePath = 'build-evidence/ci-display.json'
)

$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:RUNNER_OS -ne 'Windows') {
    throw 'This display setup is restricted to disposable GitHub-hosted Windows runners.'
}

# Use only modes advertised by the current display driver. The UI tests still
# create real native windows and inspect their actual DPR and rendered pixels.
# No registry update, custom display driver or Qt geometry override is used.
# The higher-DPR matrix separately uses the repository's existing render-only
# viewport fixture and verifies its full native client and RHI image dimensions.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class SwirlCiDisplay {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct Mode {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string deviceName;
        public ushort specVersion, driverVersion, size, driverExtra;
        public uint fields;
        public int positionX, positionY;
        public uint orientation, fixedOutput;
        public short color, duplex, yResolution, ttOption, collate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string formName;
        public ushort logPixels;
        public uint bitsPerPixel, width, height, displayFlags, frequency;
        public uint icmMethod, icmIntent, mediaType, ditherType;
        public uint reserved1, reserved2, panningWidth, panningHeight;
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool EnumDisplaySettingsW(string deviceName, uint number, ref Mode mode);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern int ChangeDisplaySettingsExW(string deviceName, ref Mode mode, IntPtr hwnd, uint flags, IntPtr parameter);

    public static Mode? Read(uint number) {
        var mode = new Mode();
        mode.size = checked((ushort)Marshal.SizeOf<Mode>());
        if (mode.size != 220) throw new InvalidOperationException("Unexpected DEVMODEW layout.");
        return EnumDisplaySettingsW(null, number, ref mode) ? mode : (Mode?)null;
    }

    public static int Test(Mode mode) {
        return ChangeDisplaySettingsExW(null, ref mode, IntPtr.Zero, 2, IntPtr.Zero);
    }

    public static int Apply(Mode mode) {
        return ChangeDisplaySettingsExW(null, ref mode, IntPtr.Zero, 0, IntPtr.Zero);
    }
}
'@

function Describe-Mode($Mode) {
    if ($null -eq $Mode) { return $null }
    return [ordered]@{ width=$Mode.width; height=$Mode.height; bitsPerPixel=$Mode.bitsPerPixel; frequency=$Mode.frequency }
}

$result = 'failed'
$before = [SwirlCiDisplay]::Read([uint32]::MaxValue)
$after = $null
$attempts = @()
$modes = @()
try {
    if ($null -eq $before) { throw 'Cannot read the current Windows display mode.' }
    for ([uint32]$index = 0; ; ++$index) {
        $mode = [SwirlCiDisplay]::Read($index)
        if ($null -eq $mode) { break }
        $modes += $mode
    }
    $after = $before
    if ($after.width -lt $MinimumWidth -or $after.height -lt $MinimumHeight) {
        $candidates = @($modes | Where-Object { $_.width -ge $MinimumWidth -and $_.height -ge $MinimumHeight -and $_.bitsPerPixel -ge 32 } | Sort-Object @{Expression={ [long]$_.width * $_.height }}, @{Expression={ $_.frequency }; Descending=$true})
        foreach ($candidate in $candidates) {
            $test = [SwirlCiDisplay]::Test($candidate)
            $apply = $null
            if ($test -eq 0) { $apply = [SwirlCiDisplay]::Apply($candidate) }
            $after = [SwirlCiDisplay]::Read([uint32]::MaxValue)
            $attempts += [ordered]@{ mode=(Describe-Mode $candidate); testResult=$test; applyResult=$apply; observed=(Describe-Mode $after) }
            if ($apply -eq 0 -and $null -ne $after -and $after.width -ge $MinimumWidth -and $after.height -ge $MinimumHeight) { break }
        }
    }
    if ($null -eq $after -or $after.width -lt $MinimumWidth -or $after.height -lt $MinimumHeight) {
        throw "The runner cannot provide the required native UI desktop. See $EvidencePath for supported modes; UI test cases have not been narrowed."
    }
    $result = 'passed'
    Write-Host "Native CI display: $($before.width)x$($before.height) -> $($after.width)x$($after.height). Physical Windows 11 display acceptance remains unverified."
} finally {
    $directory = Split-Path -Parent $EvidencePath
    if ($directory) { New-Item -ItemType Directory -Force -Path $directory | Out-Null }
    [ordered]@{
        source_sha=$env:GITHUB_SHA; result=$result; minimumWidth=$MinimumWidth; minimumHeight=$MinimumHeight
        before=(Describe-Mode $before); after=(Describe-Mode $after)
        advertisedModes=@($modes | ForEach-Object { Describe-Mode $_ }); attempts=$attempts
        physical_windows11_display_acceptance='not-run'
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $EvidencePath -Encoding utf8
}
