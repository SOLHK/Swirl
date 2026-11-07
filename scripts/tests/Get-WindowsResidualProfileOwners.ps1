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
function Read-OwnerUtc([object]$Value) {
    # ConvertFrom-Json may materialize ISO dates as DateTime on PowerShell 7.
    # The launcher has already checked the exact serialized UTC representation.
    if($Value -is [DateTime] -and $Value.Kind -eq [DateTimeKind]::Utc){$Value=$Value.ToString('o',[Globalization.CultureInfo]::InvariantCulture)}
    [DateTime]$parsed=[DateTime]::MinValue
    if($Value -isnot [string] -or $Value -cnotmatch '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{7}Z$' -or
       -not [DateTime]::TryParseExact($Value,'o',[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::RoundtripKind,[ref]$parsed) -or
       $parsed.Kind -ne [DateTimeKind]::Utc){throw 'OwnerDiagnosticEventWindowInvalid'}
    return $parsed
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
    $originalAuthenticationId=$null
    $authenticationProperty=$request.PSObject.Properties['original_child_authentication_id']
    if($null -ne $authenticationProperty -and $null -ne $authenticationProperty.Value){
        if($authenticationProperty.Value -isnot [string] -or $authenticationProperty.Value -cnotmatch '^[0-9a-f]{16}$'){throw 'OwnerDiagnosticLogonIdentityInvalid'}
        $originalAuthenticationId=[string]$authenticationProperty.Value
    }
    $profile=Assert-OwnerPlainPath ([string]$request.profile_path) $true $false
    if(-not [IO.Directory]::Exists($profile) -or $profile -ine [IO.Path]::GetFullPath([string]$request.token_profile_path) -or
       [IO.Path]::GetFileName($profile.TrimEnd('\','/')) -ine $request.username -or
       $profile -ieq [Environment]::GetFolderPath('UserProfile') -or
       $ownerOutput.StartsWith($profile.TrimEnd('\','/')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'OwnerDiagnosticProfileBindingInvalid'}
    $lifecycleTimes=New-Object 'System.Collections.Generic.List[DateTime]'
    foreach($name in @('account_creation_started','account_creation_returned','profile_creation_started','profile_loaded_observed','cleanup_decision_frozen')){
        $lifecycleTimes.Add((Read-OwnerUtc $request.profile_lifecycle_utc.$name))
    }
    for($index=1;$index -lt $lifecycleTimes.Count;$index++){
        if($lifecycleTimes[$index] -lt $lifecycleTimes[$index-1]){throw 'OwnerDiagnosticEventWindowInvalid'}
    }
    $eventStart=Read-OwnerUtc $request.event_window_start_utc;$eventEnd=Read-OwnerUtc $request.event_window_end_utc
    if($eventStart -ne $lifecycleTimes[0] -or $eventEnd -ne $lifecycleTimes[4] -or
       $eventEnd -le $eventStart -or ($eventEnd-$eventStart).TotalSeconds -gt 3600){throw 'OwnerDiagnosticEventWindowInvalid'}
    $eventStartUtc=$eventStart.ToString('o',[Globalization.CultureInfo]::InvariantCulture)
    $eventEndUtc=$eventEnd.ToString('o',[Globalization.CultureInfo]::InvariantCulture)
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
        scope='Observed residual files and ancestors within the verified disposable profile, exact-SID process metadata and exact-identity profile event metadata; no file contents, formatted event messages, target shutdown, deletion, hive unload or command-line/environment reads.'
        rm_internal_registry_writes=$true;resource_attribution_scope='Batch union: an owner uses at least one registered path; per-file ownership is not inferred.'
        no_owner_result_proves_unlocked=$false;query_after_frozen_cleanup_failure=$true;original_profile_removed=$false
        original_child_authentication_id=$originalAuthenticationId;original_child_authentication_id_known=($null -ne $originalAuthenticationId)
        rm_observation_completed=$false;exact_sid_process_snapshot=$null;residual_path_observation=$null;profile_events=$null;event_filter_controls=$null
        files=@($fileEvidence.ToArray());file_count=$files.Count;file_limit=32;owner_limit=64;get_list_call_limit=2
        rm_start_attempted=$false;rm_start_return=$null;rm_register_return=$null;rm_get_list_calls=@();rm_end_return=$null
        session_started=$false;session_end_confirmed=$false;session_end_error=$null;listing_complete=$false;owners=@();owners_identity_complete=$false
        observation_completed=$false;error=$null}
    Save-OwnerObservation
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using System.Xml;

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
  [StructLayout(LayoutKind.Sequential)] public struct Luid { public uint Low; public int High; }
  [StructLayout(LayoutKind.Sequential)] public struct TokenStatistics {
    public Luid TokenId,AuthenticationId;public long ExpirationTime;
    public uint TokenType,ImpersonationLevel,DynamicCharged,DynamicAvailable,GroupCount,PrivilegeCount;
    public Luid ModifiedId;
  }
  public sealed class SidProcessEvidence {
    public uint pid,observed_pid;public string creation_filetime,token_user_sid,authentication_id,image_name,image_path_sha256;
    public bool? running,same_logon_as_original_child,token_handle_closed,process_handle_closed;
    public bool identity_from_one_process_handle;public string error_operation,statistics_error_operation,image_error_operation;
    public int? win32_error,statistics_error,image_query_error,token_close_error,process_close_error;
  }
  public sealed class SidProcessSnapshot {
    public int pid_capacity=4096,match_limit=32,work_budget_ms=2000,enumerated,attempted,other_sid,skipped_pid_zero,unidentified,unattempted;
    public int handles_opened,handles_closed,close_failures,error_bucket_limit=32,other_error_count;
    public bool enumeration_complete,scan_attempts_complete,identity_coverage_complete,budget_exhausted,truncated;
    public bool handles_closed_confirmed=true;public double elapsed_ms;public string state="starting",error_operation;
    public int? win32_error,exception_hresult;
    public string scope="Primary-token SID snapshot only; a match does not prove file ownership. SYSTEM services or impersonating threads are outside this attribution.";
    public Dictionary<string,int> errors=new Dictionary<string,int>();
    public List<SidProcessEvidence> matches=new List<SidProcessEvidence>();
  }
  [StructLayout(LayoutKind.Sequential)] public struct FileAttributeTag { public uint Attributes,Tag; }
  [StructLayout(LayoutKind.Sequential)] public struct FileIdentity { public ulong Volume,Low,High; }
  public sealed class FileOpenEvidence {
    public uint desired_access,share_mode=7,creation_disposition=3,flags;
    public bool attempted,opened;public bool? path_scope_confirmed,regular_kind_confirmed,handle_closed;
    public string error_operation,volume_serial,file_id,final_path_sha256;public uint? attributes,reparse_tag;
    public int? win32_error,close_error,exception_hresult;public double elapsed_ms;
  }
  public sealed class ResidualPathEvidence {
    public string relative_path;public bool expected_directory;public FileOpenEvidence metadata_open,delete_access_open;
    public bool? same_file_object_for_delete_open;public string security_sddl,security_sddl_sha256,security_owner_sid,security_error;
    public int? security_win32_error,security_descriptor_bytes,security_sddl_characters;
    public bool security_sddl_truncated;public bool delete_operation_performed=false;
  }
  public sealed class ResidualPathObservation {
    public int path_limit=16,work_budget_ms=2000,requested_paths,attempted_paths,unattempted_paths;
    public int descriptor_byte_limit=16384,sddl_character_limit=2048;
    public bool completed,budget_exhausted,truncated,metadata_coverage_complete,handles_closed_confirmed=true;
    public double elapsed_ms;public string state="starting",error_operation;public int? exception_hresult;
    public string scope="Metadata and access-open observations only. No file contents, deletion, disposition, ACL change or privilege adjustment. Open success is not deletion success.";
    public List<ResidualPathEvidence> paths=new List<ResidualPathEvidence>();
  }
  [StructLayout(LayoutKind.Explicit,Size=16)] public struct EventVariant {
    [FieldOffset(0)] public int Boolean;
    [FieldOffset(8)] public uint Count;
    [FieldOffset(12)] public uint Type;
  }
  public sealed class ProfileEventEvidence {
    public string channel,provider,time_utc,record_id,activity_id,related_activity_id;
    public ushort event_id;
    public List<string> identity_matches=new List<string>();
    public Dictionary<string,string> numeric_error_fields=new Dictionary<string,string>();
    public bool numeric_fields_truncated;
  }
  public sealed class ProfileEventFilterResult {
    public string reason;public ProfileEventEvidence record;
  }
  public sealed class ProfileEventControls {
    public bool success;public int total,passed;public List<string> failures=new List<string>();
    public string scope="Synthetic XML through the actual collector filter; no log access or native APIs.";
  }
  public sealed class ProfileEventLogEvidence {
    public string channel,state="not-started",query_sha256,error_operation,limit_reason;
    public bool? enabled;public bool query_exhausted,truncated,budget_exhausted,handles_closed_confirmed=true;
    public int? win32_error,exception_hresult,next_terminal_win32;
    public int returned_records,rejected_records,handles_opened,handles_closed;
    public List<int> close_errors=new List<int>();
    public List<ProfileEventEvidence> records=new List<ProfileEventEvidence>();
    public double elapsed_ms;
  }
  public sealed class ProfileEventObservation {
    public string state="starting",source_sha,request_sha256,window_start_utc,window_end_utc;
    public string provider="Microsoft-Windows-User Profiles Service";
    public string scope="Only the fixed provider, frozen UTC window and exact SID or profile-root field equality; no formatted message, raw XML or arbitrary event-data strings are retained. Zero records do not establish a cause or successful cleanup.";
    public string query_coverage="System Security UserID, EventData Data and immediate UserData payload fields. Message-only identities, deeper payloads and nonexact path spellings are outside coverage; no broad fallback.";
    public string byte_budget_basis="Before XML rendering, reserve at most three UTF-8 bytes per non-NUL UTF-16 code unit; actual rendered UTF-8 bytes are counted, never persisted.";
    public string deadline_scope="Two-second cooperative work budget, checked between native calls. Only EvtNext receives a native timeout; EvtQuery, EvtRender and handle closing can overrun it. The existing external eight-second owned-worker cancellation trigger remains unchanged; OS exit is confirmed separately.";
    public int work_budget_ms=2000,record_limit=32,event_xml_utf8_byte_limit=16384,total_xml_utf8_byte_limit=65536;
    public int native_render_buffer_byte_limit=10924,returned_records,retained_records,rendered_xml_utf8_bytes;
    public bool collection_complete,budget_exhausted,truncated,handles_closed_confirmed=true;
    public bool? zero_matching_records;public bool cleanup_decision_changed=false,log_configuration_changed=false;
    public double elapsed_ms;public List<ProfileEventLogEvidence> logs=new List<ProfileEventLogEvidence>();
  }
  public static partial class Native {
    const string ProfileProvider="Microsoft-Windows-User Profiles Service";
    const string ProfileOperational="Microsoft-Windows-User Profile Service/Operational";
    const string EventNamespace="http://schemas.microsoft.com/win/2004/08/events/event";
    [DllImport("wevtapi.dll",CharSet=CharSet.Unicode,ExactSpelling=true,SetLastError=true)] static extern IntPtr EvtOpenChannelConfig(IntPtr session,string channel,uint flags);
    [DllImport("wevtapi.dll",ExactSpelling=true,SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool EvtGetChannelConfigProperty(IntPtr channel,int property,uint flags,uint bytes,out EventVariant value,out uint used);
    [DllImport("wevtapi.dll",CharSet=CharSet.Unicode,ExactSpelling=true,SetLastError=true)] static extern IntPtr EvtQuery(IntPtr session,string path,string query,uint flags);
    [DllImport("wevtapi.dll",ExactSpelling=true,SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool EvtNext(IntPtr query,uint capacity,[Out] IntPtr[] events,uint timeout,uint flags,out uint returned);
    [DllImport("wevtapi.dll",ExactSpelling=true,SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool EvtRender(IntPtr context,IntPtr item,uint flags,uint bytes,IntPtr buffer,out uint used,out uint properties);
    [DllImport("wevtapi.dll",ExactSpelling=true,SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool EvtClose(IntPtr handle);
    static DateTime EventUtc(string text) {
      DateTime value;
      if(text==null||!Regex.IsMatch(text,@"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{7}Z$")||
         !DateTime.TryParseExact(text,"o",CultureInfo.InvariantCulture,DateTimeStyles.RoundtripKind,out value)||value.Kind!=DateTimeKind.Utc)
        throw new ArgumentException("EventWindowInvalid");
      return value;
    }
    static XmlElement EventChild(XmlElement parent,string name) {
      XmlElement found=null;
      foreach(XmlNode node in parent.ChildNodes) {
        var element=node as XmlElement;
        if(element!=null&&element.LocalName==name&&element.NamespaceURI==EventNamespace) {
          if(found!=null)throw new FormatException("DuplicateEventElement");found=element;
        }
      }
      return found;
    }
    static string EventText(XmlElement parent,string name) {
      var child=EventChild(parent,name);if(child==null)throw new FormatException("MissingEventElement");return child.InnerText;
    }
    static string EventGuid(XmlElement correlation,string name) {
      if(correlation==null||!correlation.HasAttribute(name))return null;
      Guid value;if(!Guid.TryParse(correlation.GetAttribute(name),out value))throw new FormatException("EventGuidInvalid");
      return value.ToString("D");
    }
    static void EventPayloadField(ProfileEventEvidence result,XmlElement field,string name,string kind,string sid,string profile) {
      foreach(XmlNode child in field.ChildNodes)if(child is XmlElement)return;
      string value=field.InnerText;
      if(value==sid&&!result.identity_matches.Contains(kind+"-sid"))result.identity_matches.Add(kind+"-sid");
      if(value==profile&&!result.identity_matches.Contains(kind+"-profile-root"))result.identity_matches.Add(kind+"-profile-root");
      string numericName=(name??"").ToLowerInvariant();
      if(numericName!="error"&&numericName!="errorcode"&&numericName!="errorvalue"&&numericName!="status"&&
         numericName!="result"&&numericName!="hresult"&&numericName!="win32error"&&numericName!="dwerror"&&numericName!="resultcode")return;
      long number;
      if(Regex.IsMatch(value,@"^0[xX][0-9a-fA-F]{1,8}$"))number=Convert.ToInt64(value.Substring(2),16);
      else if(!Regex.IsMatch(value,@"^-?[0-9]{1,10}$")||!Int64.TryParse(value,NumberStyles.AllowLeadingSign,CultureInfo.InvariantCulture,out number))return;
      if(number<Int32.MinValue||number>UInt32.MaxValue)return;
      string key=kind+"."+numericName;
      if(result.numeric_error_fields.Count>=8||result.numeric_error_fields.ContainsKey(key)){result.numeric_fields_truncated=true;return;}
      result.numeric_error_fields.Add(key,unchecked((uint)number).ToString("x8"));
    }
    // This pure function is also the implementation exercised by the controls.
    // Never return the input XML, arbitrary payload values or a formatted message.
    public static ProfileEventFilterResult FilterProfileEvent(string xml,string channel,string sid,string profile,string start,string end) {
      var decision=new ProfileEventFilterResult();
      try {
        if(xml==null||new UTF8Encoding(false,true).GetByteCount(xml)>16384){decision.reason="xml-byte-limit";return decision;}
        var settings=new XmlReaderSettings { DtdProcessing=DtdProcessing.Prohibit,XmlResolver=null,MaxCharactersInDocument=16384,IgnoreComments=true,IgnoreProcessingInstructions=true };
        var document=new XmlDocument { XmlResolver=null };
        using(var input=new StringReader(xml))using(var reader=XmlReader.Create(input,settings))document.Load(reader);
        var root=document.DocumentElement;
        if(root==null||root.LocalName!="Event"||root.NamespaceURI!=EventNamespace)throw new FormatException("EventRootInvalid");
        var system=EventChild(root,"System");if(system==null)throw new FormatException("EventSystemMissing");
        var provider=EventChild(system,"Provider");var created=EventChild(system,"TimeCreated");
        if((channel!="Application"&&channel!=ProfileOperational)||provider==null||provider.GetAttribute("Name")!=ProfileProvider||EventText(system,"Channel")!=channel){decision.reason="provider-or-channel-mismatch";return decision;}
        string systemTime=created==null?null:created.GetAttribute("SystemTime");
        if(systemTime==null||!Regex.IsMatch(systemTime,@"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,7})?Z$"))
          throw new FormatException("EventUtcFormatUnknown");
        DateTime when=XmlConvert.ToDateTime(systemTime,XmlDateTimeSerializationMode.Utc);
        if(when<EventUtc(start)||when>EventUtc(end)){decision.reason="outside-frozen-window";return decision;}
        var result=new ProfileEventEvidence { channel=channel,provider=ProfileProvider,time_utc=when.ToString("o",CultureInfo.InvariantCulture) };
        ushort eventId;ulong recordId;
        if(!UInt16.TryParse(EventText(system,"EventID"),NumberStyles.None,CultureInfo.InvariantCulture,out eventId)||
           !UInt64.TryParse(EventText(system,"EventRecordID"),NumberStyles.None,CultureInfo.InvariantCulture,out recordId))throw new FormatException("EventIdentityInvalid");
        result.event_id=eventId;result.record_id=recordId.ToString(CultureInfo.InvariantCulture);
        var correlation=EventChild(system,"Correlation");result.activity_id=EventGuid(correlation,"ActivityID");result.related_activity_id=EventGuid(correlation,"RelatedActivityID");
        var security=EventChild(system,"Security");if(security!=null&&security.GetAttribute("UserID")==sid)result.identity_matches.Add("system-security-sid");
        var data=EventChild(root,"EventData");
        if(data!=null)foreach(XmlNode node in data.ChildNodes) {
          var field=node as XmlElement;
          if(field!=null&&field.LocalName=="Data"&&field.NamespaceURI==EventNamespace)EventPayloadField(result,field,field.GetAttribute("Name"),"event-data",sid,profile);
        }
        var userData=EventChild(root,"UserData");
        if(userData!=null)foreach(XmlNode container in userData.ChildNodes)if(container is XmlElement)
          foreach(XmlNode node in container.ChildNodes) {var field=node as XmlElement;if(field!=null)EventPayloadField(result,field,field.LocalName,"user-data",sid,profile);}
        if(result.identity_matches.Count==0){decision.reason="exact-identity-absent";return decision;}
        decision.record=result;decision.reason="accepted";
      }catch(Exception){decision.reason="invalid-structured-event";}
      return decision;
    }
    static void CloseEventHandle(ref IntPtr handle,ProfileEventLogEvidence log) {
      if(handle==IntPtr.Zero)return;
      try {
        bool closed=EvtClose(handle);int error=closed?0:Marshal.GetLastWin32Error();
        if(closed)log.handles_closed++;else {log.handles_closed_confirmed=false;if(log.close_errors.Count<8)log.close_errors.Add(error);}
      }catch(Exception error){log.handles_closed_confirmed=false;log.error_operation=log.error_operation??"EvtCloseException";log.exception_hresult=error.HResult;}
      finally{handle=IntPtr.Zero;}
    }
    static bool EventBudgetExpired(ProfileEventObservation result,ProfileEventLogEvidence log,Stopwatch watch) {
      if(watch.ElapsedMilliseconds<result.work_budget_ms)return false;
      result.budget_exhausted=true;log.budget_exhausted=true;log.state="time-budget-exhausted";return true;
    }
    static void EventNativeError(ProfileEventLogEvidence log,string operation,int error) {
      log.error_operation=operation;log.win32_error=error;
      log.state=error==5?"access-denied":error==1460?"native-timeout":"native-error";
    }
    static void EventLimit(ProfileEventObservation result,ProfileEventLogEvidence log,string reason) {
      result.truncated=true;log.truncated=true;log.limit_reason=reason;log.state="truncated";
    }
    public static string ProfileEventQuery(string sid,string profile,string start,string end) {
      DateTime from=EventUtc(start),to=EventUtc(end);
      if(to<=from||(to-from).TotalSeconds>3600||sid==null||!Regex.IsMatch(sid,@"^S-1-5-21-(?:[0-9]+-){3}[0-9]+$")||
         profile==null||!Regex.IsMatch(profile,@"^[A-Za-z]:\\")||profile.IndexOf('"')>=0||profile.Length>2048)
        throw new ArgumentException("EventScopeInvalid");
      // A raw XPath query, not QueryList XML: backslashes and ampersands remain
      // literal. A double-quoted profile literal permits apostrophes; the
      // previously verified ordinary Windows path cannot contain double quotes.
      return "*[System[Provider[@Name='"+ProfileProvider+"'] and TimeCreated[@SystemTime >= '"+start+"' and @SystemTime <= '"+end+"']] and (System[Security[@UserID='"+sid+"']] or EventData[Data='"+sid+"' or Data=\""+profile+"\"] or UserData[*[*='"+sid+"' or *=\""+profile+"\"]])]";
    }
    static void ReadProfileEventLog(ProfileEventObservation result,ProfileEventLogEvidence log,string sid,string profile,Stopwatch watch) {
      IntPtr config=IntPtr.Zero,query=IntPtr.Zero;var logWatch=Stopwatch.StartNew();
      try {
        if(EventBudgetExpired(result,log,watch))return;
        log.state="opening-existing-log";config=EvtOpenChannelConfig(IntPtr.Zero,log.channel,0);
        if(config==IntPtr.Zero){EventNativeError(log,"EvtOpenChannelConfig",Marshal.GetLastWin32Error());return;}log.handles_opened++;
        EventVariant enabled;uint used;
        try {
          if(EventBudgetExpired(result,log,watch))return;
          if(!EvtGetChannelConfigProperty(config,0,0,16,out enabled,out used)){EventNativeError(log,"EvtGetChannelConfigProperty",Marshal.GetLastWin32Error());return;}
          if(used!=16||enabled.Type!=13){log.error_operation="ChannelEnabledVariantInvalid";log.state="unknown-log-state";return;}
          log.enabled=enabled.Boolean!=0;
        }finally{CloseEventHandle(ref config,log);}
        if(log.enabled!=true){log.state="disabled";return;}
        if(EventBudgetExpired(result,log,watch))return;
        string filter=ProfileEventQuery(sid,profile,result.window_start_utc,result.window_end_utc);
        log.query_sha256=Hash(filter);
        query=EvtQuery(IntPtr.Zero,log.channel,filter,0x201); // channel path, reverse chronological order; no tolerant/fallback query.
        if(query==IntPtr.Zero){EventNativeError(log,"EvtQuery",Marshal.GetLastWin32Error());return;}log.handles_opened++;log.state="reading";
        while(!EventBudgetExpired(result,log,watch)) {
          if(result.returned_records>=result.record_limit){EventLimit(result,log,"record-limit");break;}
          var items=new IntPtr[1];uint count=0;
          try {
            uint remaining=(uint)Math.Max(1,result.work_budget_ms-watch.ElapsedMilliseconds);
            bool next=EvtNext(query,1,items,remaining,0,out count);int nextError=next?0:Marshal.GetLastWin32Error();
            if(items[0]!=IntPtr.Zero)log.handles_opened++;
            if(!next) {
              log.next_terminal_win32=nextError;
              if(nextError==259){log.query_exhausted=true;log.state=log.records.Count==0?"no-matching-records":"observed";}
              else EventNativeError(log,"EvtNext",nextError);
              break;
            }
            if(count!=1||items[0]==IntPtr.Zero){log.error_operation="EventHandleCountInvalid";log.state="invalid-native-result";break;}
            result.returned_records++;log.returned_records++;
            if(EventBudgetExpired(result,log,watch))break;
            uint needed,properties;
            bool sized=EvtRender(IntPtr.Zero,items[0],1,0,IntPtr.Zero,out needed,out properties);
            int sizeError=sized?0:Marshal.GetLastWin32Error();
            if(sized||sizeError!=122){EventNativeError(log,"EvtRenderSize",sizeError);break;}
            if(needed<2||(needed&1)!=0||needed>result.native_render_buffer_byte_limit){EventLimit(result,log,"render-buffer-limit");break;}
            int reservedUtf8=3*((int)needed/2-1);
            if(reservedUtf8>result.event_xml_utf8_byte_limit||result.rendered_xml_utf8_bytes+reservedUtf8>result.total_xml_utf8_byte_limit){EventLimit(result,log,"xml-utf8-byte-limit");break;}
            if(EventBudgetExpired(result,log,watch))break;
            IntPtr buffer=Marshal.AllocHGlobal((int)needed);
            try {
              uint written;
              if(!EvtRender(IntPtr.Zero,items[0],1,needed,buffer,out written,out properties)){EventNativeError(log,"EvtRender",Marshal.GetLastWin32Error());break;}
              if(written<2||written>needed||(written&1)!=0||Marshal.ReadInt16(buffer,(int)written-2)!=0){log.error_operation="EventRenderLengthInvalid";log.state="invalid-native-result";break;}
              string xml=Marshal.PtrToStringUni(buffer,(int)written/2-1);
              int utf8=new UTF8Encoding(false,true).GetByteCount(xml);result.rendered_xml_utf8_bytes+=utf8;
              var filtered=FilterProfileEvent(xml,log.channel,sid,profile,result.window_start_utc,result.window_end_utc);
              if(filtered.record==null){log.rejected_records++;}
              else {log.records.Add(filtered.record);result.retained_records++;if(filtered.record.numeric_fields_truncated)EventLimit(result,log,"numeric-field-limit");}
            }finally{Marshal.FreeHGlobal(buffer);}
            if(log.truncated)break;
          }finally{CloseEventHandle(ref items[0],log);}
        }
      }catch(Exception error){log.error_operation="ProfileEventObservationFailed";log.exception_hresult=error.HResult;log.state="exception";}
      finally{CloseEventHandle(ref query,log);CloseEventHandle(ref config,log);logWatch.Stop();log.elapsed_ms=logWatch.Elapsed.TotalMilliseconds;}
    }
    public static ProfileEventObservation ObserveProfileEvents(string sid,string profile,string start,string end,string source,string requestHash) {
      var result=new ProfileEventObservation { source_sha=source,request_sha256=requestHash,window_start_utc=start,window_end_utc=end };
      ProfileEventQuery(sid,profile,start,end); // Reject query-boundary mistakes before any log API.
      var watch=Stopwatch.StartNew();
      foreach(string channel in new string[]{"Application",ProfileOperational}) {
        var log=new ProfileEventLogEvidence { channel=channel };result.logs.Add(log);ReadProfileEventLog(result,log,sid,profile,watch);
      }
      watch.Stop();result.elapsed_ms=watch.Elapsed.TotalMilliseconds;result.collection_complete=true;
      foreach(var log in result.logs) {
        result.handles_closed_confirmed&=log.handles_closed_confirmed;
        result.collection_complete&=log.enabled==true&&log.query_exhausted&&!log.truncated&&!log.budget_exhausted&&log.error_operation==null&&log.rejected_records==0&&log.handles_closed_confirmed;
      }
      result.collection_complete&=!result.truncated&&!result.budget_exhausted&&result.elapsed_ms<=result.work_budget_ms;
      if(result.collection_complete)result.zero_matching_records=result.retained_records==0;
      result.state=result.collection_complete?"completed":"incomplete";return result;
    }
    static string ControlEvent(string payload,string security) {
      return "<Event xmlns='"+EventNamespace+"'><System><Provider Name='"+ProfileProvider+"'/><EventID>1500</EventID><TimeCreated SystemTime='2026-11-07T00:00:30.0000000Z'/><EventRecordID>123</EventRecordID><Correlation ActivityID='{01234567-89ab-cdef-0123-456789abcdef}'/><Channel>Application</Channel><Security UserID='"+security+"'/></System>"+payload+"</Event>";
    }
    public static ProfileEventControls RunEventFilterControls() {
      var result=new ProfileEventControls();string sid="S-1-5-21-1-2-3-1001",profile=@"C:\Users\swci_012345abcdef";
      string start="2026-11-07T00:00:00.0000000Z",end="2026-11-07T00:01:00.0000000Z";
      string identity="<EventData><Data Name='UserSid'>"+sid+"</Data></EventData>";
      var cases=new List<Tuple<string,string,bool>> {
        Tuple.Create("system-security-exact-sid",ControlEvent("",sid),true),
        Tuple.Create("event-data-exact-sid",ControlEvent(identity,"S-1-5-18"),true),
        Tuple.Create("event-data-exact-profile",ControlEvent("<EventData><Data Name='ProfilePath'>"+profile+"</Data></EventData>","S-1-5-18"),true),
        Tuple.Create("user-data-exact-sid",ControlEvent("<UserData><Profile xmlns='urn:profile'><UserSid>"+sid+"</UserSid></Profile></UserData>","S-1-5-18"),true),
        Tuple.Create("user-data-exact-profile",ControlEvent("<UserData><Profile xmlns='urn:profile'><ProfilePath>"+profile+"</ProfilePath></Profile></UserData>","S-1-5-18"),true),
        Tuple.Create("other-sid",ControlEvent(identity.Replace(sid,sid+"0"),"S-1-5-18"),false),
        Tuple.Create("profile-prefix-not-equality",ControlEvent("<EventData><Data Name='ProfilePath'>"+profile+"_other</Data></EventData>","S-1-5-18"),false),
        Tuple.Create("descendant-not-root-equality",ControlEvent("<EventData><Data Name='ProfilePath'>"+profile+"\\AppData</Data></EventData>","S-1-5-18"),false),
        Tuple.Create("message-substring-not-identity",ControlEvent("<EventData><Data Name='Detail'>message "+sid+" "+profile+"</Data></EventData>","S-1-5-18"),false),
        Tuple.Create("wrong-provider",ControlEvent(identity,"S-1-5-18").Replace(ProfileProvider,"OtherProvider"),false),
        Tuple.Create("wrong-channel",ControlEvent(identity,"S-1-5-18").Replace("<Channel>Application</Channel>","<Channel>Security</Channel>"),false),
        Tuple.Create("before-window",ControlEvent(identity,"S-1-5-18").Replace("00:00:30.0000000Z","00:00:00.0000000Z").Replace("2026-11-07T00:00:00","2026-11-06T23:59:59"),false),
        Tuple.Create("after-window",ControlEvent(identity,"S-1-5-18").Replace("00:00:30.0000000Z","00:01:00.0000001Z"),false),
        Tuple.Create("missing-timezone-rejected",ControlEvent(identity,"S-1-5-18").Replace("00:00:30.0000000Z","00:00:30.0000000"),false),
        Tuple.Create("explicit-offset-not-windows-z",ControlEvent(identity,"S-1-5-18").Replace("00:00:30.0000000Z","00:00:30.0000000+00:00"),false),
        Tuple.Create("exact-window-start",ControlEvent(identity,"S-1-5-18").Replace("00:00:30.0000000Z","00:00:00.0000000Z"),true),
        Tuple.Create("exact-window-end",ControlEvent(identity,"S-1-5-18").Replace("00:00:30.0000000Z","00:01:00.0000000Z"),true),
        Tuple.Create("wrong-namespace",ControlEvent(identity,"S-1-5-18").Replace(EventNamespace,"urn:untrusted"),false),
        Tuple.Create("dtd-prohibited","<!DOCTYPE Event [<!ENTITY identity '"+sid+"'>]>"+ControlEvent(identity.Replace(sid,"&identity;"),"S-1-5-18"),false),
        Tuple.Create("utf8-byte-limit",ControlEvent(identity+"<Padding>"+new string('\u00e9',9000)+"</Padding>","S-1-5-18"),false)
      };
      foreach(var item in cases) {
        bool passed=(FilterProfileEvent(item.Item2,"Application",sid,profile,start,end).record!=null)==item.Item3;
        result.total++;if(passed)result.passed++;else result.failures.Add(item.Item1);
      }
      var numeric=FilterProfileEvent(ControlEvent("<EventData><Data Name='UserSid'>"+sid+"</Data><Data Name='ErrorValue'>0x80070020</Data><Data Name='Detail'>PRIVATE_MARKER</Data></EventData>","S-1-5-18"),"Application",sid,profile,start,end).record;
      result.total++;if(numeric!=null&&numeric.numeric_error_fields.Count==1&&numeric.numeric_error_fields.ContainsKey("event-data.errorvalue")&&numeric.numeric_error_fields["event-data.errorvalue"]=="80070020")result.passed++;else result.failures.Add("numeric-error-only-no-arbitrary-detail");
      result.total++;
      if(FilterProfileEvent(ControlEvent(identity,"S-1-5-18").Replace("<Channel>Application</Channel>","<Channel>"+ProfileOperational+"</Channel>"),ProfileOperational,sid,profile,start,end).record!=null)result.passed++;
      else result.failures.Add("operational-channel-exact-identity");
      result.total++;
      try {System.Xml.XPath.XPathExpression.Compile(ProfileEventQuery(sid,@"C:\Users\a'b&c\swci_012345abcdef",start,end));result.passed++;}
      catch(Exception){result.failures.Add("raw-xpath-backslash-apostrophe-ampersand-syntax");}
      result.total++;
      try {ProfileEventQuery(sid,"C:\\Users\\bad\"path",start,end);result.failures.Add("double-quote-profile-rejected");}
      catch(ArgumentException){result.passed++;}
      result.success=result.total==result.passed;return result;
    }
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool K32EnumProcesses([Out] uint[] pids,uint bytes,out uint returned);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateFileW(string path,uint access,uint share,IntPtr security,uint disposition,uint flags,IntPtr template);
    [DllImport("kernel32.dll",SetLastError=true,EntryPoint="GetFileInformationByHandleEx")] static extern bool ReadFileAttributes(IntPtr file,int type,out FileAttributeTag value,uint bytes);
    [DllImport("kernel32.dll",SetLastError=true,EntryPoint="GetFileInformationByHandleEx")] static extern bool ReadFileIdentity(IntPtr file,int type,out FileIdentity value,uint bytes);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern uint GetFinalPathNameByHandleW(IntPtr file,StringBuilder path,uint capacity,uint flags);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool GetKernelObjectSecurity(IntPtr handle,uint information,byte[] descriptor,uint bytes,out uint needed);
    static string AuthenticationId(IntPtr token,out int? error,out string operation) {
      error=null;operation=null;uint size=(uint)Marshal.SizeOf(typeof(TokenStatistics));
      if(size!=56){operation="TokenStatisticsLayoutUnknown";return null;}
      IntPtr data=Marshal.AllocHGlobal((int)size);
      try {
        uint returned;if(!GetTokenInformation(token,10,data,size,out returned)){error=Marshal.GetLastWin32Error();operation="GetTokenInformation";return null;}
        if(returned!=size){operation="TokenStatisticsLengthUnknown";return null;}
        var value=(TokenStatistics)Marshal.PtrToStructure(data,typeof(TokenStatistics));
        return (((ulong)(uint)value.AuthenticationId.High<<32)|value.AuthenticationId.Low).ToString("x16");
      }finally{Marshal.FreeHGlobal(data);}
    }
    static void CountError(SidProcessSnapshot result,string operation,int error) {
      string key=operation+":"+error.ToString();int count;
      if(result.errors.TryGetValue(key,out count))result.errors[key]=count+1;
      else if(result.errors.Count<result.error_bucket_limit)result.errors.Add(key,1);else result.other_error_count++;
    }
    public static SidProcessSnapshot ObserveExactSid(string expectedSid,string originalAuthenticationId) {
      var result=new SidProcessSnapshot();var watch=Stopwatch.StartNew();
      try {
        var pids=new uint[result.pid_capacity];uint returned;
        if(!K32EnumProcesses(pids,(uint)(pids.Length*4),out returned)){result.error_operation="K32EnumProcesses";result.win32_error=Marshal.GetLastWin32Error();return result;}
        if(returned%4!=0||returned>pids.Length*4){result.error_operation="ProcessEnumerationLengthInvalid";return result;}
        result.enumerated=(int)(returned/4);result.enumeration_complete=returned<pids.Length*4;result.truncated=!result.enumeration_complete;
        for(int index=0;index<result.enumerated;index++) {
          if(watch.ElapsedMilliseconds>=result.work_budget_ms){result.budget_exhausted=true;break;}
          if(result.matches.Count>=result.match_limit){result.truncated=true;break;}
          result.attempted++;uint pid=pids[index];if(pid==0){result.skipped_pid_zero++;continue;}
          IntPtr process=IntPtr.Zero,token=IntPtr.Zero;SidProcessEvidence match=null;
          try {
            process=OpenProcess(0x1000|0x00100000,false,pid);
            if(process==IntPtr.Zero){result.unidentified++;CountError(result,"OpenProcess",Marshal.GetLastWin32Error());continue;}
            result.handles_opened++;
            if(!OpenProcessToken(process,0x0008,out token)){result.unidentified++;CountError(result,"OpenProcessToken",Marshal.GetLastWin32Error());continue;}
            result.handles_opened++;uint needed;bool sized=GetTokenInformation(token,1,IntPtr.Zero,0,out needed);
            int sizeError=sized?0:Marshal.GetLastWin32Error();
            if((!sized&&sizeError!=122)||needed==0||needed>16384){result.unidentified++;CountError(result,"TokenUserSizeQuery",sizeError);continue;}
            IntPtr data=Marshal.AllocHGlobal((int)needed);string sid;
            try {
              if(!GetTokenInformation(token,1,data,needed,out needed)){result.unidentified++;CountError(result,"TokenUser",Marshal.GetLastWin32Error());continue;}
              sid=new SecurityIdentifier(Marshal.ReadIntPtr(data)).Value;
            }finally{Marshal.FreeHGlobal(data);}
            // Retain no unrelated PID, SID, image, command line or environment.
            if(sid!=expectedSid){result.other_sid++;continue;}
            match=new SidProcessEvidence {pid=pid,token_user_sid=expectedSid};result.matches.Add(match);
            match.observed_pid=GetProcessId(process);
            if(match.observed_pid==0){match.error_operation="GetProcessId";match.win32_error=Marshal.GetLastWin32Error();continue;}
            if(match.observed_pid!=pid){match.error_operation="ProcessIdentityChanged";continue;}
            FileTime created,exited,kernel,user;
            if(!GetProcessTimes(process,out created,out exited,out kernel,out user)){match.error_operation="GetProcessTimes";match.win32_error=Marshal.GetLastWin32Error();continue;}
            match.creation_filetime=Hex(created);match.identity_from_one_process_handle=true;
            uint wait=WaitForSingleObject(process,0);
            if(wait==0)match.running=false;else if(wait==258)match.running=true;
            else {match.error_operation="WaitForSingleObject";match.win32_error=Marshal.GetLastWin32Error();}
            int? statisticsError;string statisticsOperation;
            match.authentication_id=AuthenticationId(token,out statisticsError,out statisticsOperation);match.statistics_error=statisticsError;match.statistics_error_operation=statisticsOperation;
            if(match.authentication_id!=null&&!String.IsNullOrEmpty(originalAuthenticationId))match.same_logon_as_original_child=match.authentication_id==originalAuthenticationId;
            uint capacity=4096;var image=new StringBuilder((int)capacity);
            if(QueryFullProcessImageNameW(process,0,image,ref capacity)) {
              string path=image.ToString(),name=Path.GetFileName(path);match.image_path_sha256=Hash(path);
              if(name.Length<=260)match.image_name=name;else match.image_error_operation="ImageBasenameLimit";
            }else {match.image_query_error=Marshal.GetLastWin32Error();match.image_error_operation="QueryFullProcessImageNameW";}
          }catch(Exception error){result.unidentified++;CountError(result,"ProcessObservationException",error.HResult);if(match!=null)match.error_operation="ProcessObservationException";}
          finally {
            if(token!=IntPtr.Zero) {
              bool closed=CloseHandle(token);int error=closed?0:Marshal.GetLastWin32Error();
              if(closed)result.handles_closed++;else{result.close_failures++;CountError(result,"CloseToken",error);}
              if(match!=null){match.token_handle_closed=closed;if(!closed)match.token_close_error=error;}
            }
            if(process!=IntPtr.Zero) {
              bool closed=CloseHandle(process);int error=closed?0:Marshal.GetLastWin32Error();
              if(closed)result.handles_closed++;else{result.close_failures++;CountError(result,"CloseProcess",error);}
              if(match!=null){match.process_handle_closed=closed;if(!closed)match.process_close_error=error;}
            }
          }
        }
        if(watch.ElapsedMilliseconds>=result.work_budget_ms)result.budget_exhausted=true;
        result.scan_attempts_complete=result.enumeration_complete&&!result.truncated&&!result.budget_exhausted&&result.attempted==result.enumerated;
        result.identity_coverage_complete=result.scan_attempts_complete&&result.unidentified==0;
        foreach(var match in result.matches)if(!match.identity_from_one_process_handle||match.error_operation!=null||match.statistics_error_operation!=null||match.image_error_operation!=null)result.identity_coverage_complete=false;
      }catch(Exception error){result.error_operation="ProcessSnapshotFailed";result.exception_hresult=error.HResult;}
      finally {
        watch.Stop();result.elapsed_ms=watch.Elapsed.TotalMilliseconds;result.unattempted=result.enumerated-result.attempted;
        result.handles_closed_confirmed=result.handles_opened==result.handles_closed&&result.close_failures==0;
        result.state=result.scan_attempts_complete&&result.handles_closed_confirmed?"completed":"partial";
      }
      return result;
    }
  }
  public static partial class Native {
    static IntPtr OpenResidualPath(string path,string profile,bool directory,uint access,FileOpenEvidence evidence) {
      var watch=Stopwatch.StartNew();evidence.attempted=true;evidence.desired_access=access;
      evidence.flags=0x00200000u|(directory?0x02000000u:0u);
      IntPtr handle=CreateFileW(path,access,7,IntPtr.Zero,3,evidence.flags,IntPtr.Zero);
      try {
        if(handle==new IntPtr(-1)){evidence.error_operation="CreateFileW";evidence.win32_error=Marshal.GetLastWin32Error();return IntPtr.Zero;}
        evidence.opened=true;FileAttributeTag attributes;
        if(!ReadFileAttributes(handle,9,out attributes,(uint)Marshal.SizeOf(typeof(FileAttributeTag)))){evidence.error_operation="FileAttributeTagInfo";evidence.win32_error=Marshal.GetLastWin32Error();return handle;}
        evidence.attributes=attributes.Attributes;evidence.reparse_tag=attributes.Tag;
        evidence.regular_kind_confirmed=(attributes.Attributes&0x400)==0&&((attributes.Attributes&0x10)!=0)==directory;
        if(evidence.regular_kind_confirmed!=true){evidence.error_operation="ResidualPathKindChanged";return handle;}
        var finalPath=new StringBuilder(32768);uint length=GetFinalPathNameByHandleW(handle,finalPath,(uint)finalPath.Capacity,0);
        if(length==0){evidence.error_operation="GetFinalPathNameByHandleW";evidence.win32_error=Marshal.GetLastWin32Error();return handle;}
        if(length>=finalPath.Capacity){evidence.error_operation="FinalPathLengthExceeded";return handle;}
        string actual=finalPath.ToString();evidence.final_path_sha256=Hash(actual);
        string extendedPrefix=new string((char)92,2)+"?"+(char)92;
        if(actual.StartsWith(extendedPrefix,StringComparison.Ordinal))actual=actual.Substring(4);
        evidence.path_scope_confirmed=String.Equals(actual,path,StringComparison.OrdinalIgnoreCase)&&
          (String.Equals(actual,profile,StringComparison.OrdinalIgnoreCase)||actual.StartsWith(profile+"\\",StringComparison.OrdinalIgnoreCase));
        if(evidence.path_scope_confirmed!=true){evidence.error_operation="ResidualPathScopeChanged";return handle;}
        FileIdentity identity;
        if(!ReadFileIdentity(handle,18,out identity,(uint)Marshal.SizeOf(typeof(FileIdentity)))){evidence.error_operation="FileIdInfo";evidence.win32_error=Marshal.GetLastWin32Error();return handle;}
        evidence.volume_serial=identity.Volume.ToString("x16");evidence.file_id=identity.High.ToString("x16")+identity.Low.ToString("x16");
        return handle;
      }catch(Exception error){evidence.error_operation="ResidualPathObservationFailed";evidence.exception_hresult=error.HResult;return handle==new IntPtr(-1)?IntPtr.Zero:handle;}
      finally{watch.Stop();evidence.elapsed_ms=watch.Elapsed.TotalMilliseconds;}
    }
    static void CloseObservedFile(IntPtr handle,FileOpenEvidence evidence) {
      if(handle==IntPtr.Zero)return;
      evidence.handle_closed=CloseHandle(handle);if(evidence.handle_closed!=true)evidence.close_error=Marshal.GetLastWin32Error();
    }
    static void ReadResidualSecurity(IntPtr handle,ResidualPathEvidence evidence,ResidualPathObservation phase) {
      uint needed;bool sized=GetKernelObjectSecurity(handle,7,null,0,out needed);int sizeError=sized?0:Marshal.GetLastWin32Error();
      evidence.security_descriptor_bytes=(int)needed;
      if((!sized&&sizeError!=122)||needed==0||needed>phase.descriptor_byte_limit){evidence.security_error="SecurityDescriptorSizeUnavailable";evidence.security_win32_error=sizeError;return;}
      var bytes=new byte[needed];
      if(!GetKernelObjectSecurity(handle,7,bytes,needed,out needed)){evidence.security_error="GetKernelObjectSecurity";evidence.security_win32_error=Marshal.GetLastWin32Error();return;}
      var descriptor=new RawSecurityDescriptor(bytes,0);
      string sddl=descriptor.GetSddlForm(AccessControlSections.Owner|AccessControlSections.Group|AccessControlSections.Access);
      evidence.security_sddl_characters=sddl.Length;evidence.security_sddl_sha256=Hash(sddl);
      evidence.security_owner_sid=descriptor.Owner==null?null:descriptor.Owner.Value;
      if(sddl.Length<=phase.sddl_character_limit)evidence.security_sddl=sddl;
      else{evidence.security_sddl_truncated=true;evidence.security_error="SecurityDescriptorTextLimit";}
    }
    public static ResidualPathObservation ObserveResidualPaths(string profile,string[] files) {
      var result=new ResidualPathObservation();var watch=Stopwatch.StartNew();
      try {
        profile=Path.GetFullPath(profile).TrimEnd('\\');
        var paths=new SortedDictionary<string,bool>(StringComparer.OrdinalIgnoreCase);paths.Add(profile,true);
        foreach(string file in files) {
          string path=Path.GetFullPath(file);
          if(!path.StartsWith(profile+"\\",StringComparison.OrdinalIgnoreCase)){result.error_operation="ResidualPathOutsideProfile";return result;}
          bool directory=false;
          while(!String.Equals(path,profile,StringComparison.OrdinalIgnoreCase)) {
            bool previous;
            if(paths.TryGetValue(path,out previous)){if(previous!=directory){result.error_operation="ResidualPathKindConflict";return result;}break;}
            if(paths.Count>=result.path_limit){result.truncated=true;result.error_operation="ResidualPathLimit";result.requested_paths=paths.Count+1;return result;}
            paths.Add(path,directory);path=Path.GetDirectoryName(path);directory=true;
          }
        }
        result.requested_paths=paths.Count;
        foreach(var path in paths) {
          if(watch.ElapsedMilliseconds>=result.work_budget_ms){result.budget_exhausted=true;break;}
          var item=new ResidualPathEvidence {relative_path=String.Equals(path.Key,profile,StringComparison.OrdinalIgnoreCase)?".":path.Key.Substring(profile.Length+1).Replace('\\','/'),expected_directory=path.Value};
          result.paths.Add(item);result.attempted_paths++;item.metadata_open=new FileOpenEvidence();
          IntPtr metadata=IntPtr.Zero,deletion=IntPtr.Zero;
          try {
            metadata=OpenResidualPath(path.Key,profile,path.Value,0x00020080,item.metadata_open);
            if(metadata!=IntPtr.Zero&&item.metadata_open.error_operation==null)ReadResidualSecurity(metadata,item,result);
            if(!path.Value) {
              if(watch.ElapsedMilliseconds>=result.work_budget_ms){result.budget_exhausted=true;break;}
              item.delete_access_open=new FileOpenEvidence();
              // DELETE | FILE_READ_ATTRIBUTES is only an access-open probe.
              // Keep the metadata handle alive while comparing the second
              // handle's volume/file ID. Never set disposition or DELETE_ON_CLOSE.
              deletion=OpenResidualPath(path.Key,profile,false,0x00010080,item.delete_access_open);
              if(item.metadata_open.file_id!=null&&item.delete_access_open.file_id!=null)
                item.same_file_object_for_delete_open=item.metadata_open.file_id==item.delete_access_open.file_id&&item.metadata_open.volume_serial==item.delete_access_open.volume_serial;
            }
          }catch(Exception error){item.security_error="ResidualPathObservationFailed";item.metadata_open.exception_hresult=error.HResult;}
          finally{CloseObservedFile(deletion,item.delete_access_open);CloseObservedFile(metadata,item.metadata_open);}
        }
        if(watch.ElapsedMilliseconds>=result.work_budget_ms)result.budget_exhausted=true;
        result.completed=!result.truncated&&!result.budget_exhausted&&result.attempted_paths==result.requested_paths;
        result.metadata_coverage_complete=result.completed;
        foreach(var item in result.paths) {
          if(item.metadata_open==null||!item.metadata_open.attempted||(!item.expected_directory&&item.delete_access_open==null))result.completed=false;
          if(item.metadata_open==null||item.metadata_open.error_operation!=null||item.security_sddl==null)result.metadata_coverage_complete=false;
          if(item.metadata_open!=null&&item.metadata_open.opened&&item.metadata_open.handle_closed!=true)result.handles_closed_confirmed=false;
          if(!item.expected_directory) {
            if(item.delete_access_open==null||item.delete_access_open.error_operation!=null||item.same_file_object_for_delete_open!=true)result.metadata_coverage_complete=false;
            if(item.delete_access_open!=null&&item.delete_access_open.opened&&item.delete_access_open.handle_closed!=true)result.handles_closed_confirmed=false;
          }
        }
      }catch(Exception error){result.completed=false;result.error_operation="ResidualPathPhaseFailed";result.exception_hresult=error.HResult;}
      finally {
        watch.Stop();result.elapsed_ms=watch.Elapsed.TotalMilliseconds;result.unattempted_paths=result.requested_paths-result.attempted_paths;
        result.state=result.completed&&result.handles_closed_confirmed?"completed":"partial";
      }
      return result;
    }
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
    $observation['native_sizes']=[ordered]@{unique_process=[Runtime.InteropServices.Marshal]::SizeOf([type][SwirlProfileOwners.UniqueProcess]);process_info=[Runtime.InteropServices.Marshal]::SizeOf([type][SwirlProfileOwners.ProcessInfo])
        token_statistics=[Runtime.InteropServices.Marshal]::SizeOf([type][SwirlProfileOwners.TokenStatistics]);file_attribute_tag=[Runtime.InteropServices.Marshal]::SizeOf([type][SwirlProfileOwners.FileAttributeTag]);file_identity=[Runtime.InteropServices.Marshal]::SizeOf([type][SwirlProfileOwners.FileIdentity]);event_variant=[Runtime.InteropServices.Marshal]::SizeOf([type][SwirlProfileOwners.EventVariant])}
    if($observation.native_sizes.unique_process -ne 12 -or $observation.native_sizes.process_info -ne 668 -or
       $observation.native_sizes.token_statistics -ne 56 -or $observation.native_sizes.file_attribute_tag -ne 8 -or $observation.native_sizes.file_identity -ne 24 -or $observation.native_sizes.event_variant -ne 16){throw 'OwnerDiagnosticNativeLayoutMismatch'}
    $observation.event_filter_controls=[SwirlProfileOwners.Native]::RunEventFilterControls()
    $observation['event_api_binding']=[ordered]@{native_library='wevtapi.dll';native_library_scope='Static DllImport of the Windows event-log API; no managed EventLog assembly dependency.'
        xml_document_assembly=[Xml.XmlDocument].Assembly.FullName;xml_reader_assembly=[Xml.XmlReader].Assembly.FullName
        compilation_reference_mode='Existing Add-Type default references, including PowerShell 7 $PSHOME/ref; no custom ReferencedAssemblies.'}
    Save-OwnerObservation
    if(-not $observation.event_filter_controls.success){throw 'OwnerDiagnosticEventFilterControlFailed'}
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
        $observation.rm_observation_completed=$observation.listing_complete -and $observation.session_end_confirmed -and $null -eq $observation.error
        Save-OwnerObservation
    }
}
if($null -eq $observation -or -not $observation.rm_observation_completed){exit 2}
# Close and persist RM before any supplemental work. The existing external
# eight-second deadline still owns retirement; native calls can overrun a local
# work budget. An interrupted phase remains explicitly incomplete on disk.
try {
    $observation.exact_sid_process_snapshot=[ordered]@{state='starting';scan_attempts_complete=$false;handles_closed_confirmed=$null;work_budget_ms=2000}
    Save-OwnerObservation
    $observation.exact_sid_process_snapshot=[SwirlProfileOwners.Native]::ObserveExactSid([string]$request.sid,$originalAuthenticationId)
    Save-OwnerObservation
    $observation.residual_path_observation=[ordered]@{state='starting';completed=$false;handles_closed_confirmed=$null;work_budget_ms=2000;path_limit=16}
    Save-OwnerObservation
    $observation.residual_path_observation=[SwirlProfileOwners.Native]::ObserveResidualPaths($profile,$files.ToArray())
    Save-OwnerObservation
    $observation.profile_events=[ordered]@{state='starting';collection_complete=$false;handles_closed_confirmed=$null;work_budget_ms=2000;record_limit=32
        source_sha=[string]$request.source_sha;request_sha256=$RequestSha256;window_start_utc=$eventStartUtc;window_end_utc=$eventEndUtc
        event_xml_utf8_byte_limit=16384;total_xml_utf8_byte_limit=65536;zero_matching_records=$null;cleanup_decision_changed=$false}
    Save-OwnerObservation
    $observation.profile_events=[SwirlProfileOwners.Native]::ObserveProfileEvents([string]$request.sid,$profile,$eventStartUtc,$eventEndUtc,[string]$request.source_sha,$RequestSha256)
    $observation.observation_completed=$observation.rm_observation_completed -and
        $observation.exact_sid_process_snapshot.scan_attempts_complete -and $observation.exact_sid_process_snapshot.handles_closed_confirmed -and
        $null -eq $observation.exact_sid_process_snapshot.error_operation -and
        $observation.residual_path_observation.completed -and $observation.residual_path_observation.handles_closed_confirmed -and
        $null -eq $observation.residual_path_observation.error_operation -and
        $observation.profile_events.collection_complete -and $observation.profile_events.handles_closed_confirmed
    if(-not $observation.observation_completed){$observation.error='OwnerDiagnosticSupplementalIncomplete'}
}catch{$observation.error='OwnerDiagnosticSupplementalFailed';$observation.observation_completed=$false}
finally{Save-OwnerObservation}
if($null -eq $observation -or -not $observation.observation_completed){exit 2}
exit 0
