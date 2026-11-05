param([Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $IsWindows -or $env:GITHUB_ACTIONS -cne 'true') { throw 'This observation requires a GitHub Windows runner.' }
$windows = [Environment]::GetFolderPath('Windows')
$system = Join-Path $windows 'System32'
$executable = Join-Path $system 'WindowsPowerShell/v1.0/powershell.exe'
$modules = Join-Path $system 'WindowsPowerShell/v1.0/Modules'
if (-not [IO.Path]::IsPathFullyQualified($windows) -or -not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw 'Fixed system Windows PowerShell is unavailable.'
}
$systemDrive = [IO.Path]::GetPathRoot($windows).TrimEnd('\')
$commandText = @'
$p = [Environment]::GetFolderPath([Environment+SpecialFolder]::CommonApplicationData)
$valid = -not [string]::IsNullOrWhiteSpace($p) -and [IO.Path]::GetPathRoot($p) -match '^[A-Za-z]:\\$'
[Console]::Write('SWIRL_PS_BOOT_OK|' + [int]$valid)
'@
$results = [Collections.Generic.List[object]]::new()
try {
    foreach ($case in @('inherited-system-modules','broker-four-variable-plus-system-modules','broker-with-system-drive')) {
        $start = [Diagnostics.ProcessStartInfo]::new()
        $start.FileName = $executable
        $start.UseShellExecute = $false
        $start.CreateNoWindow = $true
        $start.RedirectStandardInput = $true
        $start.RedirectStandardOutput = $true
        $start.RedirectStandardError = $true
        foreach ($argument in @('-NoLogo','-NoProfile','-NonInteractive','-Command',$commandText)) {
            $start.ArgumentList.Add($argument)
        }
        if ($case -ne 'inherited-system-modules') {
            $start.Environment.Clear()
            $start.Environment['SystemRoot'] = $windows
            $start.Environment['WINDIR'] = $windows
            $start.Environment['PATH'] = $system
            $start.Environment['ComSpec'] = Join-Path $system 'cmd.exe'
            if ($case -eq 'broker-with-system-drive') { $start.Environment['SystemDrive'] = $systemDrive }
        }
        $start.Environment['PSModulePath'] = $modules
        $process = [Diagnostics.Process]::new()
        $process.StartInfo = $start
        try {
            if (-not $process.Start()) { throw 'Fixed PowerShell process did not start.' }
            $process.StandardInput.Close()
            $stdout = $process.StandardOutput.ReadToEndAsync()
            $stderr = $process.StandardError.ReadToEndAsync()
            $timedOut = -not $process.WaitForExit(10000)
            if ($timedOut) { $process.Kill($true) }
            $exited = $process.WaitForExit(2000)
            $outDone = $stdout.Wait(1000)
            $errDone = $stderr.Wait(1000)
            $outText = if ($outDone) { $stdout.Result } else { '' }
            $errText = if ($errDone) { $stderr.Result } else { '' }
            $hresults = @([regex]::Matches($errText,'(?i)\b(?:0x[0-9a-f]{8}|8009001d)\b') | ForEach-Object { $_.Value.ToUpperInvariant() } | Sort-Object -Unique)
            $results.Add([ordered]@{case=$case;exitCode=$(if ($exited) { $process.ExitCode } else { $null });
                timedOut=$timedOut;markerOk=($outDone -and $outText -cin @('SWIRL_PS_BOOT_OK|0','SWIRL_PS_BOOT_OK|1'));
                knownFolderValid=($outDone -and $outText -ceq 'SWIRL_PS_BOOT_OK|1');
                stderrHRESULT=$hresults;stdoutLength=$outText.Length;stderrLength=$errText.Length})
            if (-not $exited -or -not $outDone -or -not $errDone) { throw 'PowerShell observation did not finish bounded cleanup.' }
        } finally { $process.Dispose() }
    }
} finally {
    $parent = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($OutputPath))
    [IO.Directory]::CreateDirectory($parent) | Out-Null
    $json = ConvertTo-Json -InputObject @($results.ToArray()) -Depth 3
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath), $json, [Text.UTF8Encoding]::new($false))
    Write-Output $json
}
# This is an observation, not a replacement for the authenticated product gate.
