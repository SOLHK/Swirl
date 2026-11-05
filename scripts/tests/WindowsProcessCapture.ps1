# Shared by actual installer acceptance and the x86 Windows PowerShell 5.1 regression.
# Process.Start retains the creation handle; never reconstruct a Process from its PID.
function Start-SwirlCapturedProcess {
    param([string]$Executable,[string]$Arguments,[string]$WorkingDirectory,[string]$StdoutPath,[string]$StderrPath)
    $process=New-Object Diagnostics.Process
    $capture=[pscustomobject]@{Process=$process;Started=$false;Exited=$false;ExitCode=$null;CreatedHandleRetained=$false;Stdout=$null;Stderr=$null;Readers=@();OutputsComplete=$false;ForcedTermination=$false;Closed=$false}
    try {
        $capture.Stdout=[IO.File]::Open($StdoutPath,[IO.FileMode]::Create,[IO.FileAccess]::Write,[IO.FileShare]::Read)
        $capture.Stderr=[IO.File]::Open($StderrPath,[IO.FileMode]::Create,[IO.FileAccess]::Write,[IO.FileShare]::Read)
        $process.StartInfo.FileName=$Executable;$process.StartInfo.Arguments=$Arguments
        $process.StartInfo.WorkingDirectory=$WorkingDirectory
        $process.StartInfo.UseShellExecute=$false;$process.StartInfo.CreateNoWindow=$true
        $process.StartInfo.RedirectStandardOutput=$true;$process.StartInfo.RedirectStandardError=$true
        if(-not $process.Start()){throw 'The actual child process did not start.'}
        $capture.Started=$true
        $capture.CreatedHandleRetained=$process.Handle -ne [IntPtr]::Zero
        if(-not $capture.CreatedHandleRetained){throw 'The created child process handle is unavailable.'}
        # Drain both native byte streams concurrently, without PowerShell event
        # callbacks on threads which have no runspace, or an unbounded string buffer.
        $capture.Readers=@($process.StandardOutput.BaseStream.CopyToAsync($capture.Stdout),$process.StandardError.BaseStream.CopyToAsync($capture.Stderr))
        return $capture
    }catch {
        $failure=$_
        if($capture.Started){try{if(-not $process.HasExited){$process.Kill();$null=$process.WaitForExit(5000)}}catch{}}
        if($null -ne $capture.Stdout){$capture.Stdout.Dispose()}
        if($null -ne $capture.Stderr){$capture.Stderr.Dispose()}
        $process.Dispose()
        throw $failure
    }
}
function Complete-SwirlCapturedOutput([object]$Capture) {
    if($Capture.OutputsComplete){return}
    if($Capture.Readers.Count -ne 2 -or -not [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]$Capture.Readers,5000)){throw 'Actual child output pipes did not reach EOF within the bounded drain period.'}
    $Capture.Stdout.Flush();$Capture.Stderr.Flush();$Capture.OutputsComplete=$true
}
function Wait-SwirlCapturedProcess([object]$Capture,[int]$TimeoutMilliseconds) {
    $Capture.Exited=$Capture.Process.WaitForExit($TimeoutMilliseconds)
    if(-not $Capture.Exited){return $false}
    $code=$Capture.Process.ExitCode
    if($null -eq $code){throw 'The actual native process exit code is unavailable; null is not success.'}
    $Capture.ExitCode=$code
    Complete-SwirlCapturedOutput $Capture
    return $true
}
function Close-SwirlCapturedProcess([object]$Capture) {
    if($null -eq $Capture -or $Capture.Closed){return}
    try {
        if($Capture.Started) {
            if(-not $Capture.Process.HasExited){$Capture.ForcedTermination=$true;$Capture.Process.Kill();if(-not $Capture.Process.WaitForExit(5000)){throw 'Actual child did not exit during bounded cleanup.'}}
            $Capture.Exited=$Capture.Process.HasExited
            $code=$Capture.Process.ExitCode
            if($null -eq $code){throw 'The actual native process exit code is unavailable during cleanup; null is not success.'}
            $Capture.ExitCode=$code
            Complete-SwirlCapturedOutput $Capture
        }
    }finally {
        if($null -ne $Capture.Stdout){$Capture.Stdout.Dispose()}
        if($null -ne $Capture.Stderr){$Capture.Stderr.Dispose()}
        $Capture.Process.Dispose();$Capture.Closed=$true
    }
}
