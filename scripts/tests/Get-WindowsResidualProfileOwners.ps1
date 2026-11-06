param(
    [Parameter(Mandatory=$true)][string]$RequestPath,
    [Parameter(Mandatory=$true)][string]$RequestSha256,
    [Parameter(Mandatory=$true)][string]$OutputPath
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
# Target-query-only collector. Restart Manager maintains its own registry-backed
# session; this is not a claim that Windows performs no internal writes.
# Never call RmShutdown/RmRestart, stop an owner, unload a hive or delete a profile.
if($env:OS -ne 'Windows_NT' -or $env:GITHUB_ACTIONS -ne 'true' -or
   $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:SWIRL_DISPOSABLE_INSTALL_TEST -ne '1' -or
   $PSVersionTable.PSVersion.Major -ne 7 -or -not [Environment]::Is64BitProcess){exit 2}

function Assert-OwnerPlainPath([string]$Path,[bool]$MustExist,[bool]$RegularFile) {
    if($Path -notmatch '^[A-Za-z]:\\' -or $Path.Substring(2) -match '[/:<>"|?*\x00-\x1f]'){throw 'OwnerDiagnosticLocalPathRequired'}
    foreach($part in $Path.Substring(3).TrimEnd('\').Split('\')){
        if($Path.Length -gt 3 -and ($part -in @('','.','..') -or $part -match '[. ]$' -or
           $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)')){throw 'OwnerDiagnosticLocalPathRequired'}
    }
    $full=[IO.Path]::GetFullPath($Path)
    $current=$full
    while($current){
        $exists=$true;$attributes=$null
        try{$attributes=[IO.File]::GetAttributes($current)}
        catch [IO.FileNotFoundException]{$exists=$false}
        catch [IO.DirectoryNotFoundException]{$exists=$false}
        if($exists){
            if($attributes -band [IO.FileAttributes]::ReparsePoint){throw 'OwnerDiagnosticLinkedPathRejected'}
            if($current -ceq $full -and $RegularFile -and ($attributes -band [IO.FileAttributes]::Directory)){throw 'OwnerDiagnosticRegularFileRequired'}
        }elseif($current -ceq $full -and $MustExist){throw 'OwnerDiagnosticPathUnavailable'}
        $parent=[IO.Path]::GetDirectoryName($current)
        if($parent -eq $current){break};$current=$parent
    }
    return $full
}
function Owner-Hash([byte[]]$Bytes) {
    $sha=[Security.Cryptography.SHA256]::Create()
    try{return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}
    finally{$sha.Dispose()}
}
function Save-OwnerObservation {
    [void](Assert-OwnerPlainPath $script:ownerOutput $false $true)
    $temporary=$script:ownerOutput+'.tmp'
    [void](Assert-OwnerPlainPath $temporary $false $true)
    [IO.File]::WriteAllText($temporary,($script:observation|ConvertTo-Json -Depth 12),(New-Object Text.UTF8Encoding $false))
    [IO.File]::Move($temporary,$script:ownerOutput,$true)
}

$observation=$null;$sessionStarted=$false;[uint32]$session=0
try {
    $requestFile=Assert-OwnerPlainPath $RequestPath $true $true
    $ownerOutput=Assert-OwnerPlainPath $OutputPath $false $true
    if([IO.File]::Exists($ownerOutput) -or [IO.Directory]::Exists($ownerOutput) -or
       [IO.Path]::GetDirectoryName($requestFile) -cne [IO.Path]::GetDirectoryName($ownerOutput) -or
       [IO.Path]::GetFileName($ownerOutput) -cne 'owner-worker.json' -or $RequestSha256 -cnotmatch '^[0-9a-f]{64}$'){throw 'OwnerDiagnosticOutputBindingInvalid'}
    $stream=[IO.File]::Open($requestFile,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    try {
        if($stream.Length -gt 262144){throw 'OwnerDiagnosticInputTooLarge'}
        $memory=New-Object IO.MemoryStream
        try{$stream.CopyTo($memory);$bytes=$memory.ToArray()}finally{$memory.Dispose()}
    }finally{$stream.Dispose()}
    if($bytes.Length -gt 262144 -or (Owner-Hash $bytes) -cne $RequestSha256){throw 'OwnerDiagnosticRequestDigestMismatch'}
    $request=[Text.Encoding]::UTF8.GetString($bytes).TrimStart([char]0xfeff)|ConvertFrom-Json
    foreach($name in @('new_account_created','profile_removed','path_verified','token_path_verified')){
        if($request.$name -isnot [bool]){throw 'OwnerDiagnosticFrozenFailureRequired'}
    }
    foreach($name in @('profile_path_exists','profile_key_exists','user_hive_loaded','user_classes_hive_loaded')){
        if($request.final_state.$name -isnot [bool]){throw 'OwnerDiagnosticFrozenFailureRequired'}
    }
    if(($request.schema -isnot [int] -and $request.schema -isnot [long]) -or $request.schema -ne 1 -or
       ($request.cleanup_deadline_ms -isnot [int] -and $request.cleanup_deadline_ms -isnot [long]) -or
       ($request.cleanup_elapsed_ms -isnot [int] -and $request.cleanup_elapsed_ms -isnot [long] -and $request.cleanup_elapsed_ms -isnot [double]) -or
       $request.new_account_created -ne $true -or $request.profile_removed -ne $false -or
       $request.path_verified -ne $true -or $request.token_path_verified -ne $true -or
       $request.cleanup_deadline_ms -ne 30000 -or -not [double]::IsFinite([double]$request.cleanup_elapsed_ms) -or $request.cleanup_elapsed_ms -lt 30000 -or
       $request.source_sha -cnotmatch '^[0-9a-f]{40}$' -or $request.source_sha -cne $env:GITHUB_SHA -or
       $request.sid -cnotmatch '^S-1-5-21-(?:[0-9]+-){3}[0-9]+$' -or $request.username -cnotmatch '^swci_[0-9a-f]{12}$' -or
       $request.final_state.profile_path_exists -ne $true -or $request.final_state.profile_key_exists -ne $false -or
       $request.final_state.user_hive_loaded -ne $false -or $request.final_state.user_classes_hive_loaded -ne $false){throw 'OwnerDiagnosticFrozenFailureRequired'}
    $profile=Assert-OwnerPlainPath ([string]$request.profile_path) $true $false
    if(-not [IO.Directory]::Exists($profile) -or $profile -ine [IO.Path]::GetFullPath([string]$request.token_profile_path) -or
       [IO.Path]::GetFileName($profile.TrimEnd('\','/')) -ine $request.username -or
       $profile -ieq [Environment]::GetFolderPath('UserProfile') -or
       $ownerOutput.StartsWith($profile.TrimEnd('\','/')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'OwnerDiagnosticProfileBindingInvalid'}
    $entries=@($request.files)
    if($entries.Count -lt 1 -or $entries.Count -gt 32){throw 'OwnerDiagnosticFileLimit'}
    $files=New-Object 'System.Collections.Generic.List[string]'
    $fileEvidence=New-Object 'System.Collections.Generic.List[object]'
    $seen=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach($entry in $entries){
        $relative=[string]$entry.relative_path
        if($entry.kind -cne 'file' -or $null -ne $entry.hresult -or $relative.Length -gt 2048 -or
           [string]::IsNullOrWhiteSpace($relative) -or $relative.Contains('\') -or $relative.Contains(':') -or $relative.Contains([char]0) -or
           ([long]$entry.attributes -band 0x410) -or [long]$entry.bytes -lt 0 -or -not $seen.Add($relative)){throw 'OwnerDiagnosticRegularFilesRequired'}
        foreach($part in $relative.Split('/')){
            if($part -in @('','.','..') -or $part -match '[. ]$' -or $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)'){throw 'OwnerDiagnosticRelativePathRejected'}
        }
        $file=Assert-OwnerPlainPath (Join-Path $profile $relative) $true $true
        if(-not $file.StartsWith($profile.TrimEnd('\','/')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'OwnerDiagnosticFileOutsideProfile'}
        $attributes=[IO.File]::GetAttributes($file)
        $files.Add($file)
        $fileEvidence.Add([ordered]@{relative_path=$relative;observed_bytes=[long]$entry.bytes;current_bytes=(New-Object IO.FileInfo $file).Length;current_attributes=[int]$attributes})
    }
    $observation=[ordered]@{schema=1;source_sha=[string]$request.source_sha;request_sha256=$RequestSha256
        worker_script_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
        powershell_major=$PSVersionTable.PSVersion.Major;powershell_version=$PSVersionTable.PSVersion.ToString();process_bits=64
        scope='Only the observed ordinary files inside the verified disposable profile; no target shutdown, deletion, hive unload or command-line/environment reads.'
        rm_internal_registry_writes=$true;resource_attribution_scope='Batch union: an owner uses at least one registered path; per-file ownership is not inferred.'
        no_owner_result_proves_unlocked=$false;query_after_frozen_cleanup_failure=$true;original_profile_removed=$false
        files=@($fileEvidence.ToArray());file_count=$files.Count;file_limit=32;owner_limit=64;get_list_call_limit=2
        rm_start_attempted=$false;rm_start_return=$null;rm_register_return=$null;rm_get_list_calls=@();rm_end_return=$null
        session_started=$false;session_end_confirmed=$false;session_end_error=$null;listing_complete=$false;owners=@();owners_identity_complete=$false
        observation_completed=$false;error=$null}
    Save-OwnerObservation
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;

namespace SwirlProfileOwners {
  [StructLayout(LayoutKind.Sequential)] public struct FileTime { public uint Low,High; }
  [StructLayout(LayoutKind.Sequential)] public struct UniqueProcess { public uint Pid; public FileTime Started; }
  [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] public struct ProcessInfo {
    public UniqueProcess Process;
    [MarshalAs(UnmanagedType.ByValTStr,SizeConst=256)] public string AppName;
    [MarshalAs(UnmanagedType.ByValTStr,SizeConst=64)] public string ServiceName;
    public int ApplicationType; public uint AppStatus,SessionId;
    [MarshalAs(UnmanagedType.Bool)] public bool Restartable;
  }
  public sealed class OwnerEvidence {
    public uint pid,observed_pid,rm_session_id,rm_app_status; public int rm_application_type;
    public string rm_creation_filetime,handle_creation_filetime,token_user_sid,image_name,image_path_sha256;
    public string rm_app_name_sha256,rm_service_name,error_operation; public int? win32_error,image_query_error,token_query_error,token_close_error,process_close_error;
    public bool? process_running,token_user_matches_fresh_sid,token_handle_closed,process_handle_closed;
    public bool pid_and_creation_match; public bool? owned_job_membership=null;
    public string owned_job_membership_scope="The acceptance Job was already disposed; no membership claim is made.";
  }
  public static class Native {
    // https://learn.microsoft.com/windows/win32/api/restartmanager/nf-restartmanager-rmgetlist
    [DllImport("rstrtmgr.dll",CharSet=CharSet.Unicode)] public static extern uint RmStartSession(out uint session,uint flags,StringBuilder key);
    [DllImport("rstrtmgr.dll",CharSet=CharSet.Unicode)] public static extern uint RmRegisterResources(uint session,uint count,[In,MarshalAs(UnmanagedType.LPArray,ArraySubType=UnmanagedType.LPWStr,SizeParamIndex=1)] string[] files,uint applications,IntPtr processes,uint services,IntPtr serviceNames);
    [DllImport("rstrtmgr.dll",CharSet=CharSet.Unicode)] public static extern uint RmGetList(uint session,out uint needed,ref uint count,[In,Out] ProcessInfo[] owners,out uint rebootReasons);
    [DllImport("rstrtmgr.dll")] public static extern uint RmEndSession(uint session);
    [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr OpenProcess(uint access,bool inherit,uint pid);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint GetProcessId(IntPtr process);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetProcessTimes(IntPtr process,out FileTime created,out FileTime exited,out FileTime kernel,out FileTime user);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint WaitForSingleObject(IntPtr process,uint milliseconds);
    [DllImport("kernel32.dll",SetLastError=true,CharSet=CharSet.Unicode)] static extern bool QueryFullProcessImageNameW(IntPtr process,uint flags,StringBuilder name,ref uint length);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(IntPtr process,uint access,out IntPtr token);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool GetTokenInformation(IntPtr token,int information,IntPtr data,uint length,out uint needed);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
    static string Hex(FileTime time) {return (((ulong)time.High<<32)|time.Low).ToString("x16");}
    static string Hash(string value) {using(var sha=SHA256.Create()){return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(value ?? ""))).Replace("-","").ToLowerInvariant();}}
    public static OwnerEvidence Inspect(ProcessInfo item,string expectedSid) {
      var result=new OwnerEvidence {pid=item.Process.Pid,rm_creation_filetime=Hex(item.Process.Started),
        rm_application_type=item.ApplicationType,rm_app_status=item.AppStatus,rm_session_id=item.SessionId,
        rm_app_name_sha256=Hash(item.AppName),rm_service_name=item.ServiceName};
      IntPtr process=IntPtr.Zero,token=IntPtr.Zero;
      try {
        // One process handle anchors all observations against PID reuse. No
        // terminate, VM-read, duplicate-handle or debug privilege is requested.
        process=OpenProcess(0x1000|0x00100000,false,item.Process.Pid);
        if(process==IntPtr.Zero){result.error_operation="OpenProcess";result.win32_error=Marshal.GetLastWin32Error();return result;}
        result.observed_pid=GetProcessId(process);
        if(result.observed_pid==0){result.error_operation="GetProcessId";result.win32_error=Marshal.GetLastWin32Error();return result;}
        FileTime created,exited,kernel,user;
        if(!GetProcessTimes(process,out created,out exited,out kernel,out user)){result.error_operation="GetProcessTimes";result.win32_error=Marshal.GetLastWin32Error();return result;}
        result.handle_creation_filetime=Hex(created);
        result.pid_and_creation_match=result.observed_pid==item.Process.Pid && result.handle_creation_filetime==result.rm_creation_filetime;
        if(!result.pid_and_creation_match){result.error_operation="ProcessIdentityChanged";return result;}
        uint wait=WaitForSingleObject(process,0);
        if(wait==0)result.process_running=false;else if(wait==258)result.process_running=true;
        else {result.error_operation="WaitForSingleObject";result.win32_error=Marshal.GetLastWin32Error();}
        if(OpenProcessToken(process,0x0008,out token)) {
          uint needed;GetTokenInformation(token,1,IntPtr.Zero,0,out needed);
          if(needed==0||needed>16384){result.token_query_error=Marshal.GetLastWin32Error();}
          else {
            IntPtr data=Marshal.AllocHGlobal((int)needed);
            try {
              if(GetTokenInformation(token,1,data,needed,out needed)) {
                result.token_user_sid=new SecurityIdentifier(Marshal.ReadIntPtr(data)).Value;
                result.token_user_matches_fresh_sid=result.token_user_sid==expectedSid;
              }else result.token_query_error=Marshal.GetLastWin32Error();
            }finally{Marshal.FreeHGlobal(data);}
          }
        }else result.token_query_error=Marshal.GetLastWin32Error();
        uint capacity=4096;var image=new StringBuilder((int)capacity);
        if(QueryFullProcessImageNameW(process,0,image,ref capacity)) {
          string path=image.ToString();result.image_name=Path.GetFileName(path);result.image_path_sha256=Hash(path);
        }else result.image_query_error=Marshal.GetLastWin32Error();
      }catch(Exception){result.error_operation="OwnerIdentityObservationFailed";}
      finally {
        if(token!=IntPtr.Zero){result.token_handle_closed=CloseHandle(token);if(result.token_handle_closed!=true)result.token_close_error=Marshal.GetLastWin32Error();}
        if(process!=IntPtr.Zero){result.process_handle_closed=CloseHandle(process);if(result.process_handle_closed!=true)result.process_close_error=Marshal.GetLastWin32Error();}
      }
      return result;
    }
  }
}
'@
    $observation['native_sizes']=[ordered]@{unique_process=[Runtime.InteropServices.Marshal]::SizeOf([type][SwirlProfileOwners.UniqueProcess]);process_info=[Runtime.InteropServices.Marshal]::SizeOf([type][SwirlProfileOwners.ProcessInfo])}
    if($observation.native_sizes.unique_process -ne 12 -or $observation.native_sizes.process_info -ne 668){throw 'OwnerDiagnosticNativeLayoutMismatch'}
    $key=New-Object Text.StringBuilder 33
    $observation.rm_start_attempted=$true;Save-OwnerObservation
    $code=[SwirlProfileOwners.Native]::RmStartSession([ref]$session,0,$key)
    $observation.rm_start_return=$code
    if($code -ne 0){throw 'OwnerDiagnosticSessionStartFailed'}
    $sessionStarted=$true;$observation.session_started=$true;Save-OwnerObservation
    $code=[SwirlProfileOwners.Native]::RmRegisterResources($session,[uint32]$files.Count,$files.ToArray(),0,[IntPtr]::Zero,0,[IntPtr]::Zero)
    $observation.rm_register_return=$code;Save-OwnerObservation
    if($code -ne 0){throw 'OwnerDiagnosticResourceRegistrationFailed'}
    [uint32]$needed=0;[uint32]$count=0;[uint32]$reboot=0
    $code=[SwirlProfileOwners.Native]::RmGetList($session,[ref]$needed,[ref]$count,$null,[ref]$reboot)
    $observation.rm_get_list_calls+=@([ordered]@{call=1;return_code=$code;needed=$needed;capacity=0;returned=$count;reboot_reasons=$reboot});Save-OwnerObservation
    if($needed -gt 64 -or $count -gt 64){throw 'OwnerDiagnosticOwnerLimit'}
    $owners=New-Object 'System.Collections.Generic.List[object]'
    if($code -eq 234 -and $needed -gt 0){
        $items=New-Object 'SwirlProfileOwners.ProcessInfo[]' ([int]$needed)
        $count=$needed;$capacity=$needed
        $code=[SwirlProfileOwners.Native]::RmGetList($session,[ref]$needed,[ref]$count,$items,[ref]$reboot)
        $observation.rm_get_list_calls+=@([ordered]@{call=2;return_code=$code;needed=$needed;capacity=$capacity;returned=$count;reboot_reasons=$reboot});Save-OwnerObservation
        if($code -ne 0 -or $needed -gt 64 -or $count -gt $capacity){throw 'OwnerDiagnosticOwnerListIncomplete'}
        for($index=0;$index -lt $count;$index++){
            $owners.Add([SwirlProfileOwners.Native]::Inspect($items[$index],[string]$request.sid))
            $observation.owners=@($owners.ToArray());Save-OwnerObservation
        }
    }elseif($code -ne 0 -or $needed -ne 0 -or $count -ne 0){throw 'OwnerDiagnosticOwnerListIncomplete'}
    $observation.listing_complete=$true
    $observation.owners_identity_complete=@($owners.ToArray()|Where-Object {
        -not $_.pid_and_creation_match -or $null -eq $_.token_user_matches_fresh_sid -or
        $null -ne $_.error_operation -or $null -ne $_.image_query_error -or $null -ne $_.token_query_error -or
        $_.process_handle_closed -ne $true -or $_.token_handle_closed -ne $true
    }).Count -eq 0
}catch{
    if($null -ne $observation){
        $code=$_.Exception.Message
        $observation.error=if($code -cmatch '^OwnerDiagnostic[A-Za-z]+$'){$code}else{'OwnerDiagnosticObservationFailed'}
    }
}finally{
    if($sessionStarted){
        try {
            $observation.rm_end_return=[SwirlProfileOwners.Native]::RmEndSession($session)
            $observation.session_end_confirmed=$observation.rm_end_return -eq 0
        }catch{$observation.session_end_confirmed=$false;$observation.session_end_error='OwnerDiagnosticSessionEndUnconfirmed'}
    }
    if($null -ne $observation){
        $observation.observation_completed=$observation.listing_complete -and $observation.session_end_confirmed -and $null -eq $observation.error
        Save-OwnerObservation
    }
}
if($null -eq $observation -or -not $observation.observation_completed){exit 2}
exit 0
