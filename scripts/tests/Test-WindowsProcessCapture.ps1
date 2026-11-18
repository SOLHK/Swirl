param(
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory,
    [Parameter(Mandatory=$true)][string]$ExpectedUserSid,
    [Parameter(Mandatory=$true)][string]$ExpectedSourceSha
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'WindowsProcessCapture.ps1')
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal $identity
if($identity.User.Value -cne $ExpectedUserSid -or $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -or [Environment]::Is64BitProcess -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1){throw 'Process capture regression requires the real disposable x86 Windows PowerShell 5.1 standard-user process.'}
$evidence=[IO.Path]::GetFullPath($EvidenceDirectory)
[IO.Directory]::CreateDirectory($evidence)|Out-Null
$fixture=Join-Path $evidence ('fixture-'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($fixture)|Out-Null
$exe=Join-Path $fixture 'ProcessFixture.exe'
$rows=New-Object 'System.Collections.Generic.List[object]'
$report=[ordered]@{schema=1;source_sha=$ExpectedSourceSha;user_sid=$ExpectedUserSid;actual_non_admin_token=$true;actual_x86_powershell=$true;powershell_version=$PSVersionTable.PSVersion.ToString();start_api='System.Diagnostics.Process.Start';helper_sha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'WindowsProcessCapture.ps1') -Algorithm SHA256).Hash.ToLowerInvariant();fixture_sha256=$null;processes=$rows;forced_termination=$false;fixture_removed=$false;success=$false;error=$null}
try {
    # OutputAssembly without PassThru emits a real console EXE; the regression
    # invokes that EXE through the same captured-process path as normal NSIS/UI.
    Add-Type -OutputAssembly $exe -OutputType ConsoleApplication -TypeDefinition @'
using System;
using System.Text;
public static class SwirlCapturedProcessFixture {
    public static int Main(string[] args) {
        Console.OutputEncoding = new UTF8Encoding(false);
        int code = Int32.Parse(args[0]);
        if(args.Length > 1) {
            Console.Out.Write(new string('O', 131072) + "\n");
            Console.Out.Flush();
            Console.Error.Write(new string('E', 131072) + "\n");
        } else {
            Console.Out.Write("stdout:" + code + "\n");
            Console.Error.Write("stderr:" + code + "\n");
        }
        return code;
    }
}
'@
    $report.fixture_sha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    $cases=@(@{name='fast-exit-0';code=0;flood=$false;close_only=$false},@{name='fast-exit-2';code=2;flood=$false;close_only=$false},@{name='fast-exit-4';code=4;flood=$false;close_only=$false},@{name='dual-pipe-large-output';code=4;flood=$true;close_only=$false},@{name='early-ui-style-exit-4';code=4;flood=$false;close_only=$true})
    foreach($case in $cases) {
        $capture=$null
        $row=[ordered]@{name=$case.name;expected_exit_code=$case.code;exit_code=$null;exited=$false;created_handle_retained=$false;output_drains_completed=$false;stdout_exact=$false;stderr_exact=$false;stdout_bytes=0;stderr_bytes=0;forced_termination=$false;passed=$false};$rows.Add($row)
        $stdout=Join-Path $evidence ($case.name+'.stdout.log');$stderr=Join-Path $evidence ($case.name+'.stderr.log')
        $arguments=[string]$case.code;if($case.flood){$arguments+=' flood'}
        try {
            $capture=Start-SwirlCapturedProcess -Executable $exe -Arguments $arguments -WorkingDirectory $fixture -StdoutPath $stdout -StderrPath $stderr
            if($case.close_only) {
                # The ordinary UI can fail before its explicit close wait.
                # Cleanup must still preserve an already-exited child's real code.
                $watch=[Diagnostics.Stopwatch]::StartNew()
                while(-not $capture.Process.HasExited -and $watch.ElapsedMilliseconds -lt 5000){Start-Sleep -Milliseconds 10}
                if(-not $capture.Process.HasExited){throw 'The quick early-UI-exit fixture did not exit.'}
            }elseif(-not (Wait-SwirlCapturedProcess $capture 5000)){throw 'The actual process capture fixture timed out.'}
        }finally {
            if($null -ne $capture){try{Close-SwirlCapturedProcess $capture}finally{$row.exited=$capture.Exited;$row.exit_code=$capture.ExitCode;$row.created_handle_retained=$capture.CreatedHandleRetained;$row.output_drains_completed=$capture.OutputsComplete;$row.forced_termination=$capture.ForcedTermination;if($capture.ForcedTermination){$report.forced_termination=$true}}}
        }
        $out=[IO.File]::ReadAllBytes($stdout);$err=[IO.File]::ReadAllBytes($stderr)
        $expectedOut=if($case.flood){('O'*131072)+"`n"}else{"stdout:$($case.code)`n"}
        $expectedErr=if($case.flood){('E'*131072)+"`n"}else{"stderr:$($case.code)`n"}
        $row.stdout_exact=[Convert]::ToBase64String($out) -ceq [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($expectedOut))
        $row.stderr_exact=[Convert]::ToBase64String($err) -ceq [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($expectedErr))
        $row.stdout_bytes=$out.Length;$row.stderr_bytes=$err.Length
        $row.passed=$row.exited -and $null -ne $row.exit_code -and $row.exit_code -eq $case.code -and $row.created_handle_retained -and $row.output_drains_completed -and $row.stdout_exact -and $row.stderr_exact -and -not $row.forced_termination
        if(-not $row.passed){throw ('Actual process capture regression failed: '+$case.name)}
    }
    $report.success=$rows.Count -eq 5 -and -not $report.forced_termination
}catch{$report.error=$_.Exception.Message;$report.success=$false}
finally {
    try{Remove-Item -LiteralPath $fixture -Recurse -Force;$report.fixture_removed=-not [IO.Directory]::Exists($fixture)}catch{$report.success=$false;$report.error=([string]$report.error+'; fixture cleanup: '+$_.Exception.Message)}
    if(-not $report.fixture_removed){$report.success=$false}
    $report|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $evidence 'process-capture-policy.json') -Encoding UTF8
}
if(-not $report.success){throw ('Process capture regression failed: '+$report.error)}
