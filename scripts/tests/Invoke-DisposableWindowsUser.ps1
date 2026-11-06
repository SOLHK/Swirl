param(
    [Parameter(Mandatory=$true)][string]$Script,
    [Parameter(Mandatory=$true)][string]$ArgumentsFile,
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory,
    [ValidateRange(30,1800)][int]$TimeoutSeconds=600
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT' -or $env:GITHUB_ACTIONS -ne 'true' -or
    $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:SWIRL_DISPOSABLE_INSTALL_TEST -ne '1' -or
    -not [Environment]::Is64BitProcess) {
    throw 'A disposable hosted Windows runner, explicit installer opt-in and a 64-bit parent are required.'
}
$parentIdentity=[Security.Principal.WindowsIdentity]::GetCurrent()
$parentPrincipal=New-Object Security.Principal.WindowsPrincipal $parentIdentity
if (-not $parentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -or $parentIdentity.IsSystem) {
    throw 'Creating the temporary standard account requires the hosted administrator, not LocalSystem.'
}
. (Join-Path $PSScriptRoot '../RustProductPackagePolicy.ps1')
foreach ($path in @($Script,$ArgumentsFile,$EvidenceDirectory)) { Assert-SwirlPathWithoutLinks $path }
$targetScript=(Resolve-Path -LiteralPath $Script).Path
$argumentPath=(Resolve-Path -LiteralPath $ArgumentsFile).Path
$evidence=[IO.Path]::GetFullPath($EvidenceDirectory)
[IO.Directory]::CreateDirectory($evidence)|Out-Null
$argumentObject=Get-Content -LiteralPath $argumentPath -Raw -Encoding UTF8|ConvertFrom-Json
if ($argumentObject -isnot [pscustomobject] -or
    $null -ne $argumentObject.PSObject.Properties['ExpectedUserSid']) { throw 'Named child parameters must not supply ExpectedUserSid.' }

# Use documented Win32 account/profile/process APIs. No account password is
# passed to a command line, written to a file, or included in public evidence.
# https://learn.microsoft.com/windows/win32/api/winbase/nf-winbase-createprocesswithlogonw
# https://learn.microsoft.com/windows/win32/api/userenv/nf-userenv-deleteprofilew
if (-not ('SwirlDisposableUser.Native' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;

namespace SwirlDisposableUser {
  public static class Native {
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct UserInfo {
      public string Name,Password; public uint PasswordAge,Privilege;
      public string Home,Comment; public uint Flags; public string Script;
    }
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct Member { public string Name; }
    [DllImport("netapi32.dll",CharSet=CharSet.Unicode)] static extern uint NetUserAdd(string server,uint level,ref UserInfo user,out uint error);
    [DllImport("netapi32.dll",CharSet=CharSet.Unicode)] static extern uint NetUserDel(string server,string name);
    [DllImport("netapi32.dll",CharSet=CharSet.Unicode)] static extern uint NetUserGetInfo(string server,string name,uint level,out IntPtr buffer);
    [DllImport("netapi32.dll")] static extern uint NetApiBufferFree(IntPtr buffer);
    [DllImport("netapi32.dll",CharSet=CharSet.Unicode)] static extern uint NetLocalGroupAddMembers(string server,string group,uint level,ref Member member,uint count);
    [DllImport("userenv.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool DeleteProfileW(string sid,string profile,string computer);
    public static int DeleteOwnedProfile(string sid) {
      // PowerShell converts $null passed to a string parameter to "". The
      // computer argument must be a native NULL on supported Windows versions.
      return DeleteProfileW(sid,null,null) ? 0 : Marshal.GetLastWin32Error();
    }
    [DllImport("userenv.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool GetUserProfileDirectoryW(IntPtr token,StringBuilder path,ref uint length);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(IntPtr process,uint access,out IntPtr token);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool GetTokenInformation(IntPtr token,int type,IntPtr buffer,uint length,out uint returned);
    [DllImport("kernel32.dll",SetLastError=true)] public static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("user32.dll",SetLastError=true)] static extern IntPtr GetProcessWindowStation();
    [DllImport("user32.dll",SetLastError=true)] static extern IntPtr GetThreadDesktop(uint thread);
    [DllImport("user32.dll",SetLastError=true)] static extern bool GetUserObjectSecurity(IntPtr handle,ref uint info,byte[] descriptor,uint length,out uint needed);
    [DllImport("user32.dll",SetLastError=true)] static extern bool SetUserObjectSecurity(IntPtr handle,ref uint info,byte[] descriptor);

    public static void CreateUser(string name,string password) {
      var user=new UserInfo {Name=name,Password=password,Privilege=1,Flags=0x10201,Comment="Disposable Swirl hosted CI acceptance account"};
      uint invalid; uint code=NetUserAdd(null,1,ref user,out invalid); user.Password=null;
      if(code!=0) throw new Win32Exception((int)code,"NetUserAdd");
    }
    public static void AddToUsers(string name) {
      var account=(NTAccount)new SecurityIdentifier("S-1-5-32-545").Translate(typeof(NTAccount));
      string group=account.Value.Substring(account.Value.IndexOf('\\')+1);
      var member=new Member {Name=Environment.MachineName+"\\"+name};
      uint code=NetLocalGroupAddMembers(null,group,3,ref member,1);
      if(code!=0 && code!=1378) throw new Win32Exception((int)code,"NetLocalGroupAddMembers");
    }
    public static bool UserExists(string name) {
      IntPtr buffer; uint code=NetUserGetInfo(null,name,0,out buffer);
      if(buffer!=IntPtr.Zero) NetApiBufferFree(buffer);
      if(code==2221) return false;
      if(code!=0) throw new Win32Exception((int)code,"NetUserGetInfo");
      return true;
    }
    public static void RemoveUser(string name) {
      uint code=NetUserDel(null,name);
      if(code!=0 && code!=2221) throw new Win32Exception((int)code,"NetUserDel");
    }
    static byte[] Security(IntPtr handle) {
      uint info=4,needed; GetUserObjectSecurity(handle,ref info,null,0,out needed);
      if(needed==0) throw new Win32Exception(Marshal.GetLastWin32Error(),"GetUserObjectSecurity(size)");
      var bytes=new byte[needed];
      if(!GetUserObjectSecurity(handle,ref info,bytes,needed,out needed)) throw new Win32Exception(Marshal.GetLastWin32Error(),"GetUserObjectSecurity");
      return bytes;
    }
    static void SetSecurity(IntPtr handle,byte[] bytes) {
      uint info=4; if(!SetUserObjectSecurity(handle,ref info,bytes)) throw new Win32Exception(Marshal.GetLastWin32Error(),"SetUserObjectSecurity");
    }
    static byte[] Bytes(RawSecurityDescriptor descriptor) {var bytes=new byte[descriptor.BinaryLength];descriptor.GetBinaryForm(bytes,0);return bytes;}
    public sealed class AccessGrant {
      internal IntPtr Handle; internal SecurityIdentifier Sid; internal byte[] Original;
      public bool OwnAccessRemoved; public bool OriginalDaclRestored;
      internal AccessGrant(IntPtr handle,string sid,int mask) {
        Handle=handle; Sid=new SecurityIdentifier(sid); Original=Security(handle);
        var descriptor=new RawSecurityDescriptor(Original,0);
        if(descriptor.DiscretionaryAcl==null) return;
        int index=0;
        while(index<descriptor.DiscretionaryAcl.Count && (descriptor.DiscretionaryAcl[index].AceFlags&AceFlags.Inherited)==0) index++;
        descriptor.DiscretionaryAcl.InsertAce(index,new CommonAce(AceFlags.None,AceQualifier.AccessAllowed,mask,Sid,false,null));
        SetSecurity(handle,Bytes(descriptor));
      }
      public void Restore() {
        // Remove this fresh SID only, preserving unrelated concurrent ACL edits.
        var current=new RawSecurityDescriptor(Security(Handle),0);
        if(current.DiscretionaryAcl!=null) {
          for(int i=current.DiscretionaryAcl.Count-1;i>=0;i--) {
            var ace=current.DiscretionaryAcl[i] as KnownAce;
            if(ace!=null && ace.SecurityIdentifier==Sid) current.DiscretionaryAcl.RemoveAce(i);
          }
          SetSecurity(Handle,Bytes(current));
        }
        var result=new RawSecurityDescriptor(Security(Handle),0);
        OwnAccessRemoved=true;
        if(result.DiscretionaryAcl!=null) foreach(GenericAce item in result.DiscretionaryAcl) {
          var ace=item as KnownAce; if(ace!=null && ace.SecurityIdentifier==Sid) OwnAccessRemoved=false;
        }
        OriginalDaclRestored=result.GetSddlForm(AccessControlSections.Access)==new RawSecurityDescriptor(Original,0).GetSddlForm(AccessControlSections.Access);
        if(!OwnAccessRemoved) throw new InvalidOperationException("Disposable SID remains in desktop ACL");
      }
    }
    public static AccessGrant GrantWindowStation(string sid) {return new AccessGrant(GetProcessWindowStation(),sid,0xF037F);}
    public static AccessGrant GrantDesktop(string sid) {return new AccessGrant(GetThreadDesktop(GetCurrentThreadId()),sid,0xF01FF);}

    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateFileW(string path,uint access,uint share,IntPtr attributes,uint creation,uint flags,IntPtr template);
    [StructLayout(LayoutKind.Sequential)] struct AttributeTag {public uint Attributes,Tag;}
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetFileInformationByHandleEx(IntPtr file,int type,out AttributeTag data,uint length);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool GetKernelObjectSecurity(IntPtr handle,uint info,byte[] descriptor,uint length,out uint needed);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool SetKernelObjectSecurity(IntPtr handle,uint info,byte[] descriptor);
    static IntPtr OpenAclFile(string path) {
      // Bounded test-file snapshot/restore, not normal inheritance editing.
      // BACKUP_SEMANTICS permits directory handles; no backup/restore privilege
      // is enabled. READ_CONTROL | WRITE_DAC | FILE_READ_ATTRIBUTES still
      // require ordinary ACL access, including the reparse-attribute check.
      IntPtr handle=CreateFileW(path,0x00060080,7,IntPtr.Zero,3,0x02200000,IntPtr.Zero);
      if(handle==new IntPtr(-1))throw new Win32Exception(Marshal.GetLastWin32Error(),"Open test ACL file");
      AttributeTag tag;
      if(!GetFileInformationByHandleEx(handle,9,out tag,(uint)Marshal.SizeOf(typeof(AttributeTag)))) {
        int error=Marshal.GetLastWin32Error();CloseHandle(handle);throw new Win32Exception(error,"Read test file attributes");
      }
      if((tag.Attributes&0x400)!=0){CloseHandle(handle);throw new InvalidOperationException("Test ACL file is a reparse point");}
      return handle;
    }
    static RawSecurityDescriptor FileDescriptor(IntPtr handle) {
      uint needed;GetKernelObjectSecurity(handle,4,null,0,out needed);
      if(needed==0 || needed>1048576)throw new InvalidOperationException("Invalid bounded test file security descriptor");
      var bytes=new byte[needed];
      if(!GetKernelObjectSecurity(handle,4,bytes,needed,out needed))throw new Win32Exception(Marshal.GetLastWin32Error(),"Read test file DACL");
      return new RawSecurityDescriptor(bytes,0);
    }
    static void WriteFileDescriptor(IntPtr handle,RawSecurityDescriptor descriptor) {
      // Set-Acl/SetSecurityInfo migrates NT-style DACLs to automatic inheritance
      // and changes D: to D:AI. Restore raw file descriptors through the handle,
      // as documented for file-security snapshot/restore. Preserve current ACEs
      // and control bits; do not propagate changes into existing descendants.
      // https://learn.microsoft.com/windows/win32/fileio/file-security-and-access-rights
      if((descriptor.ControlFlags&ControlFlags.DiscretionaryAclAutoInherited)!=0)
        descriptor.SetFlags(descriptor.ControlFlags|ControlFlags.DiscretionaryAclAutoInheritRequired);
      if(!SetKernelObjectSecurity(handle,4,Bytes(descriptor)))throw new Win32Exception(Marshal.GetLastWin32Error(),"Write test file DACL");
    }
    public static string FileAclSddl(string path) {
      IntPtr handle=OpenAclFile(path);
      try{return FileDescriptor(handle).GetSddlForm(AccessControlSections.Access);}finally{CloseHandle(handle);}
    }
    public static void GrantFileAccess(string path,string sid,int mask,bool inherit) {
      IntPtr handle=OpenAclFile(path);
      try {
        var descriptor=FileDescriptor(handle);
        if(descriptor.DiscretionaryAcl==null)return;
        int index=0;
        while(index<descriptor.DiscretionaryAcl.Count && (descriptor.DiscretionaryAcl[index].AceFlags&AceFlags.Inherited)==0)index++;
        AceFlags flags=inherit ? AceFlags.ContainerInherit|AceFlags.ObjectInherit : AceFlags.None;
        descriptor.DiscretionaryAcl.InsertAce(index,new CommonAce(flags,AceQualifier.AccessAllowed,mask|0x00100000,new SecurityIdentifier(sid),false,null));
        WriteFileDescriptor(handle,descriptor);
      }finally{CloseHandle(handle);}
    }
    public static void RemoveFileAccess(string path,string sid) {
      IntPtr handle=OpenAclFile(path);
      try {
        var descriptor=FileDescriptor(handle);var identity=new SecurityIdentifier(sid);bool changed=false;
        if(descriptor.DiscretionaryAcl!=null)for(int i=descriptor.DiscretionaryAcl.Count-1;i>=0;i--) {
          var ace=descriptor.DiscretionaryAcl[i] as KnownAce;
          if(ace!=null && ace.SecurityIdentifier==identity){descriptor.DiscretionaryAcl.RemoveAce(i);changed=true;}
        }
        if(changed)WriteFileDescriptor(handle,descriptor);
      }finally{CloseHandle(handle);}
    }

    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct Startup {
      public uint Size;public string Reserved,Desktop,Title;
      public uint X,Y,XSize,YSize,XCount,YCount,Fill,Flags;public ushort Show,ReservedSize;
      public IntPtr ReservedData,Input,Output,Error;
    }
    [StructLayout(LayoutKind.Sequential)] struct ProcessInfo {public IntPtr Process,Thread;public uint ProcessId,ThreadId;}
    [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcessWithLogonW(string user,string domain,string password,uint logon,string application,StringBuilder command,uint flags,IntPtr environment,string directory,ref Startup startup,out ProcessInfo process);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateJobObjectW(IntPtr attributes,string name);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int type,ref ExtendedLimits data,uint length);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool QueryInformationJobObject(IntPtr job,int type,out Accounting data,uint length,IntPtr returned);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint ResumeThread(IntPtr thread);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint WaitForSingleObject(IntPtr handle,uint milliseconds);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetExitCodeProcess(IntPtr process,out uint code);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateJobObject(IntPtr job,uint code);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateProcess(IntPtr process,uint code);
    [StructLayout(LayoutKind.Sequential)] struct BasicLimits {
      public long ProcessTime,JobTime;public uint Flags;public UIntPtr Minimum,Maximum;
      public uint ActiveLimit;public UIntPtr Affinity;public uint Priority,Scheduling;
    }
    [StructLayout(LayoutKind.Sequential)] struct IoCounters {public ulong ReadOps,WriteOps,OtherOps,ReadBytes,WriteBytes,OtherBytes;}
    [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits {public BasicLimits Basic;public IoCounters Io;public UIntPtr ProcessMemory,JobMemory,PeakProcess,PeakJob;}
    [StructLayout(LayoutKind.Sequential)] struct Accounting {public long UserTime,KernelTime,PeriodUser,PeriodKernel;public uint PageFaults,TotalProcesses,ActiveProcesses,TerminatedProcesses;}
    public sealed class TokenEvidence {
      public string Sid,IntegritySid,ProfilePath;public bool Administrator,Elevated,System;
    }
    static TokenEvidence Token(IntPtr process) {
      // WindowsPrincipal.IsInRole duplicates a primary token for its native
      // membership check, so TOKEN_DUPLICATE is required alongside TOKEN_QUERY.
      IntPtr token;if(!OpenProcessToken(process,0x0008|0x0002,out token)) throw new Win32Exception(Marshal.GetLastWin32Error(),"OpenProcessToken");
      try {
        var result=new TokenEvidence();
        using(var identity=new WindowsIdentity(token)) {
          result.Sid=identity.User.Value;result.System=identity.IsSystem;
          result.Administrator=new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator);
        }
        uint length;IntPtr data=Marshal.AllocHGlobal(4);
        try {if(!GetTokenInformation(token,20,data,4,out length))throw new Win32Exception(Marshal.GetLastWin32Error(),"TokenElevation");result.Elevated=Marshal.ReadInt32(data)!=0;}
        finally {Marshal.FreeHGlobal(data);}
        GetTokenInformation(token,25,IntPtr.Zero,0,out length);data=Marshal.AllocHGlobal((int)length);
        try {if(!GetTokenInformation(token,25,data,length,out length))throw new Win32Exception(Marshal.GetLastWin32Error(),"TokenIntegrityLevel");result.IntegritySid=new SecurityIdentifier(Marshal.ReadIntPtr(data)).Value;}
        finally {Marshal.FreeHGlobal(data);}
        length=32768;var path=new StringBuilder((int)length);
        if(!GetUserProfileDirectoryW(token,path,ref length))throw new Win32Exception(Marshal.GetLastWin32Error(),"GetUserProfileDirectory");
        result.ProfilePath=path.ToString();return result;
      } finally {CloseHandle(token);}
    }
    public sealed class Child : IDisposable {
      IntPtr process,thread,job;public uint ProcessId;public TokenEvidence TokenInfo;public bool ForcedTermination;
      internal Child(string user,string password,string application,string command,string directory,string expectedSid) {
        job=CreateJobObjectW(IntPtr.Zero,null);
        if(job==IntPtr.Zero)throw new Win32Exception(Marshal.GetLastWin32Error(),"CreateJobObject");
        try {
          var limits=new ExtendedLimits();limits.Basic.Flags=0x2000;
          if(!SetInformationJobObject(job,9,ref limits,(uint)Marshal.SizeOf(typeof(ExtendedLimits))))throw new Win32Exception(Marshal.GetLastWin32Error(),"SetInformationJobObject");
          var startup=new Startup();startup.Size=(uint)Marshal.SizeOf(typeof(Startup));startup.Flags=1;startup.Show=0;
          ProcessInfo pi;
          if(!CreateProcessWithLogonW(user,".",password,1,application,new StringBuilder(command),0x08000404,IntPtr.Zero,directory,ref startup,out pi))throw new Win32Exception(Marshal.GetLastWin32Error(),"CreateProcessWithLogonW");
          process=pi.Process;thread=pi.Thread;ProcessId=pi.ProcessId;
          if(!AssignProcessToJobObject(job,process))throw new Win32Exception(Marshal.GetLastWin32Error(),"AssignProcessToJobObject");
          TokenInfo=Token(process);
          if(TokenInfo.Sid!=expectedSid||TokenInfo.Administrator||TokenInfo.Elevated||TokenInfo.System||TokenInfo.IntegritySid!="S-1-16-8192")throw new InvalidOperationException("Child is not the exact non-admin medium-integrity user");
        } catch(Exception startError) {
          Exception cleanupError=null;
          if(process!=IntPtr.Zero) {
            bool terminated=TerminateProcess(process,125);int terminationError=Marshal.GetLastWin32Error();
            uint wait=WaitForSingleObject(process,5000);
            if(wait!=0)cleanupError=new InvalidOperationException("Created child "+ProcessId+" did not terminate after failed startup; terminate="+terminated+", win32="+terminationError+", wait="+wait);
          }
          Dispose();
          if(cleanupError!=null)throw new AggregateException("Disposable child startup and cleanup failed",startError,cleanupError);
          throw;
        }
      }
      public void Resume() {
        if(thread==IntPtr.Zero)throw new InvalidOperationException("Child was already resumed");
        if(ResumeThread(thread)==UInt32.MaxValue)throw new Win32Exception(Marshal.GetLastWin32Error(),"ResumeThread");
        CloseHandle(thread);thread=IntPtr.Zero;
      }
      public bool Wait(uint milliseconds) {uint code=WaitForSingleObject(process,milliseconds);if(code==0)return true;if(code==258)return false;throw new Win32Exception(Marshal.GetLastWin32Error(),"WaitForSingleObject");}
      public uint ExitCode {get {uint code;if(!GetExitCodeProcess(process,out code))throw new Win32Exception(Marshal.GetLastWin32Error(),"GetExitCodeProcess");return code;}}
      public uint ActiveProcesses {get {Accounting info;if(!QueryInformationJobObject(job,1,out info,(uint)Marshal.SizeOf(typeof(Accounting)),IntPtr.Zero))throw new Win32Exception(Marshal.GetLastWin32Error(),"QueryInformationJobObject");return info.ActiveProcesses;}}
      public void KillOwned() {ForcedTermination=true;if(!TerminateJobObject(job,124))throw new Win32Exception(Marshal.GetLastWin32Error(),"TerminateJobObject");}
      public void Dispose() {if(thread!=IntPtr.Zero){CloseHandle(thread);thread=IntPtr.Zero;}if(process!=IntPtr.Zero){CloseHandle(process);process=IntPtr.Zero;}if(job!=IntPtr.Zero){CloseHandle(job);job=IntPtr.Zero;}}
    }
    public static Child Start(string user,string password,string application,string command,string directory,string sid) {return new Child(user,password,application,command,directory,sid);}
  }
}
'@
}

$userName='swci_'+[guid]::NewGuid().ToString('N').Substring(0,12)
$fixture=Join-Path 'D:\Codex\tmp\standard-user' ([guid]::NewGuid().ToString('N'))
Assert-SwirlPathWithoutLinks $fixture
[IO.Directory]::CreateDirectory($fixture)|Out-Null
$created=$false;$userSid=$null;$child=$null;$windowGrant=$null;$desktopGrant=$null
$fileGrants=New-Object 'System.Collections.Generic.List[object]'
$cleanupErrors=New-Object 'System.Collections.Generic.List[string]'
$result=[ordered]@{schema=1;success=$false;scope='A real temporary local standard user on a disposable hosted Windows runner; not a physical Windows 11 desktop.'
    username=$userName;sid=$null;parent_sid=$parentIdentity.User.Value;token=$null;child_pid=$null;child_exit_code=$null
    profile_loaded=$false;child_completed=$false;remaining_job_processes=$null;forced_termination=$false
    account_removed=$false;profile_removed=$false;desktop_access_removed=$false;window_station_access_removed=$false
    desktop_dacl_restored=$false;window_station_dacl_restored=$false
    input_acls_restored=$false;input_acl_checks=@();fixture_removed=$false;error=$null;cleanup_errors=@()}
function Add-FixtureAccessPlan([string]$Path,[Security.AccessControl.FileSystemRights]$Rights,[bool]$Inherit) {
    $before=[SwirlDisposableUser.Native]::FileAclSddl($Path)
    $fileGrants.Add([pscustomobject]@{path=$Path;before=$before;rights=$Rights;inherit=$Inherit})
}
function Grant-FixtureAccess([object]$Plan) {
    Assert-SwirlPathWithoutLinks $Plan.path
    [SwirlDisposableUser.Native]::GrantFileAccess($Plan.path,$userSid,[int]$Plan.rights,$Plan.inherit)
}
try {
    $random=New-Object byte[] 24;$rng=[Security.Cryptography.RandomNumberGenerator]::Create()
    try {$rng.GetBytes($random)} finally {$rng.Dispose()}
    $password='Sw!9'+[Convert]::ToBase64String($random)
    try {
        # Only a successful NetUserAdd establishes ownership. Existence alone
        # must never authorize deleting an account created by another process.
        if ([SwirlDisposableUser.Native]::UserExists($userName)) {throw 'Random disposable username already exists.'}
        [SwirlDisposableUser.Native]::CreateUser($userName,$password)
        $created=$true
        $userSid=(New-Object Security.Principal.NTAccount ($env:COMPUTERNAME,$userName)).Translate([Security.Principal.SecurityIdentifier]).Value
        [SwirlDisposableUser.Native]::AddToUsers($userName)
        $result.sid=$userSid
        # Snapshot every original ACL before modifying an ancestor. Arguments
        # may live inside evidence, so interleaved snapshot/grant is incorrect.
        Add-FixtureAccessPlan $fixture 'Modify' $true
        Add-FixtureAccessPlan $evidence 'Modify' $true
        Add-FixtureAccessPlan $targetScript 'ReadAndExecute' $false
        Add-FixtureAccessPlan $argumentPath 'Read' $false
        # Cross-version inputs stay outside the child's writable evidence tree.
        # Grant only these exact validated files, never the baseline directory.
        foreach($inputName in @('CrossVersionInput','BaselineInstaller','BaselineAdmission')) {
            $property=$argumentObject.PSObject.Properties[$inputName]
            if($null -ne $property) {
                $inputPath=[IO.Path]::GetFullPath([string]$property.Value)
                Assert-SwirlPathWithoutLinks $inputPath
                if(-not [IO.File]::Exists($inputPath) -or $inputPath.StartsWith($evidence.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) {throw 'Baseline inputs must be exact read-only files outside the standard-user evidence tree.'}
                $rights=if($inputName -ceq 'BaselineInstaller'){'ReadAndExecute'}else{'Read'}
                Add-FixtureAccessPlan $inputPath $rights $false
            }
        }
        foreach($plan in $fileGrants){Grant-FixtureAccess $plan}
        $windowGrant=[SwirlDisposableUser.Native]::GrantWindowStation($userSid)
        $desktopGrant=[SwirlDisposableUser.Native]::GrantDesktop($userSid)
        $parameters=[ordered]@{}
        foreach($property in $argumentObject.PSObject.Properties){$parameters[$property.Name]=$property.Value}
        $parameters.ExpectedUserSid=$userSid
        $config=[ordered]@{script=$targetScript;parameters=$parameters;evidence=$evidence;expectedSid=$userSid;parentSid=$parentIdentity.User.Value}
        $configPath=Join-Path $fixture 'request.json'
        [IO.File]::WriteAllText($configPath,($config|ConvertTo-Json -Depth 12),(New-Object Text.UTF8Encoding $false))
        $bootstrap=Join-Path $fixture 'run.ps1'
        $bootstrapText=@'
param([Parameter(Mandatory=$true)][string]$Request)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$data=Get-Content -LiteralPath $Request -Raw -Encoding UTF8|ConvertFrom-Json
$receipt=[ordered]@{schema=1;success=$false;sid=$null;is_admin=$null;is_64_bit_process=[Environment]::Is64BitProcess;profile=$null;known_folders=$null;error=$null}
try {
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    $principal=New-Object Security.Principal.WindowsPrincipal $identity
    $receipt.sid=$identity.User.Value;$receipt.is_admin=$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    $receipt.profile=[Environment]::GetFolderPath('UserProfile')
    $receipt.known_folders=@{desktop=[Environment]::GetFolderPath('Desktop');programs=[Environment]::GetFolderPath('Programs');local_app_data=[Environment]::GetFolderPath('LocalApplicationData')}
    if($receipt.sid -cne $data.expectedSid -or $receipt.sid -ceq $data.parentSid -or $receipt.is_admin -or $receipt.is_64_bit_process){throw 'Expected actual standard-user x86 Windows PowerShell process.'}
    if(-not $receipt.profile -or $env:USERPROFILE -ine $receipt.profile){throw 'Actual user profile/environment did not load.'}
    $parameters=@{};foreach($property in $data.parameters.PSObject.Properties){$parameters[$property.Name]=$property.Value}
    & $data.script @parameters *> (Join-Path $data.evidence 'standard-user-output.log')
    $receipt.success=$true
} catch {$receipt.error=$_.Exception.Message;[IO.File]::WriteAllText((Join-Path $data.evidence 'standard-user-error.log'),($_|Out-String))}
finally {$receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $data.evidence 'standard-user-child.json') -Encoding UTF8}
if(-not $receipt.success){exit 1}
'@
        [IO.File]::WriteAllText($bootstrap,$bootstrapText,(New-Object Text.UTF8Encoding $true))
        $powershell=Join-Path $env:WINDIR 'SysWOW64\WindowsPowerShell\v1.0\powershell.exe'
        if(-not (Test-Path -LiteralPath $powershell -PathType Leaf)){throw 'Actual x86 Windows PowerShell 5.1 is required.'}
        $command='"'+$powershell+'" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$bootstrap+'" -Request "'+$configPath+'"'
        if($command.Length -ge 1024){throw 'CreateProcessWithLogonW command exceeds its documented bound.'}
        $child=[SwirlDisposableUser.Native]::Start($userName,$password,$powershell,$command,$fixture,$userSid)
    } finally {$password=$null;if($null -ne $random){[Array]::Clear($random,0,$random.Length)}}
    $result.child_pid=$child.ProcessId;$result.token=$child.TokenInfo
    $result.profile_loaded=Test-Path -LiteralPath ('Registry::HKEY_USERS\'+$userSid)
    if(-not $result.profile_loaded){throw 'The new account HKCU hive is not loaded.'}
    $child.Resume()
    $watch=[Diagnostics.Stopwatch]::StartNew()
    while(-not $child.Wait(100)) {if($watch.Elapsed.TotalSeconds -ge $TimeoutSeconds){throw 'Standard-user child exceeded its bounded timeout.'}}
    $result.child_completed=$true;$result.child_exit_code=$child.ExitCode
    $children=[Diagnostics.Stopwatch]::StartNew()
    while($child.ActiveProcesses -gt 0 -and $children.Elapsed.TotalSeconds -lt 15){Start-Sleep -Milliseconds 100}
    $result.remaining_job_processes=$child.ActiveProcesses
    if($result.child_exit_code -ne 0 -or $result.remaining_job_processes -ne 0){throw 'The standard-user process failed or left descendants running.'}
    $childReceipt=Join-Path $evidence 'standard-user-child.json'
    if(-not (Test-Path -LiteralPath $childReceipt -PathType Leaf)){throw 'Standard-user completion receipt is missing.'}
    $receipt=Get-Content -LiteralPath $childReceipt -Raw|ConvertFrom-Json
    if(-not $receipt.success -or $receipt.sid -cne $userSid -or $receipt.is_admin -or $receipt.is_64_bit_process){throw 'The actual child identity/result is invalid.'}
    $result.success=$true
} catch {$result.error=$_.Exception.Message;$result['error_detail']=$_.Exception.ToString()}
finally {
    if($null -ne $child){
        try {if($child.ActiveProcesses -gt 0){$child.KillOwned();$result.forced_termination=$true;$result.success=$false;[void]$child.Wait(5000)}}
        catch {$cleanupErrors.Add('owned-process-cleanup: '+$_.Exception.Message)}
        finally {$child.Dispose()}
    }
    foreach($grant in @(@{value=$desktopGrant;field='desktop_access_removed';exact='desktop_dacl_restored'},@{value=$windowGrant;field='window_station_access_removed';exact='window_station_dacl_restored'})){
        if($null -ne $grant.value){try {$grant.value.Restore();$result[$grant.field]=$grant.value.OwnAccessRemoved;$result[$grant.exact]=$grant.value.OriginalDaclRestored}catch{$cleanupErrors.Add('desktop-acl: '+$_.Exception.Message)}}
    }
    try {
        $allFileAclsRestored=$true
        # New evidence/bootstrap files inherit this account's ACE at creation.
        # Remove only that fresh SID from current descriptors, without migrating
        # other ACLs or reverting any unrelated concurrent permission edits.
        foreach($directory in @($fixture,$evidence)){
            foreach($entry in @(Get-ChildItem -LiteralPath $directory -Recurse -Force)){
                Assert-SwirlPathWithoutLinks $entry.FullName
                [SwirlDisposableUser.Native]::RemoveFileAccess($entry.FullName,$userSid)
                if(@((Get-Acl -LiteralPath $entry.FullName).Access|Where-Object {$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -ceq $userSid}).Count){throw 'Disposable SID remains in a generated test file ACL.'}
            }
        }
        foreach($grant in $fileGrants){
            if(-not (Test-Path -LiteralPath $grant.path)){continue}
            Assert-SwirlPathWithoutLinks $grant.path
            [SwirlDisposableUser.Native]::RemoveFileAccess($grant.path,$userSid)
        }
        $aclChecks=New-Object 'System.Collections.Generic.List[object]'
        foreach($grant in $fileGrants){
            if(-not (Test-Path -LiteralPath $grant.path)){continue}
            $restored=Get-Acl -LiteralPath $grant.path
            $ownSidAbsent=@($restored.Access|Where-Object {$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -ceq $userSid}).Count -eq 0
            $after=[SwirlDisposableUser.Native]::FileAclSddl($grant.path)
            $aclChecks.Add([ordered]@{path=$grant.path;before=$grant.before;after=$after;own_sid_absent=$ownSidAbsent;restored=($after -ceq $grant.before)})
            $result.input_acl_checks=@($aclChecks.ToArray())
            if(-not $ownSidAbsent){throw 'Disposable SID remains in input/evidence ACL.'}
            if($after -cne $grant.before){$allFileAclsRestored=$false}
        }
        $result.input_acls_restored=$allFileAclsRestored
        if(-not $allFileAclsRestored){$cleanupErrors.Add('file-acl: an input DACL differs from its original state; see input_acl_checks.')}
    }catch{$cleanupErrors.Add('file-acl: '+$_.Exception.Message)}
    if($created -and $userSid){
        try {
            $profileKey='Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\'+$userSid
            $profilePath=if(Test-Path -LiteralPath $profileKey){[Environment]::ExpandEnvironmentVariables((Get-ItemProperty -LiteralPath $profileKey).ProfileImagePath)}else{$null}
            if($profilePath){
                Assert-SwirlPathWithoutLinks $profilePath
                if($profilePath -ieq [Environment]::GetFolderPath('UserProfile') -or [IO.Path]::GetFileName($profilePath) -notlike ($userName+'*')){throw 'Refusing a profile outside the newly created account.'}
                $profileWatch=[Diagnostics.Stopwatch]::StartNew();$deleted=$false;$lastProfileError=0
                do {
                    $lastProfileError=[SwirlDisposableUser.Native]::DeleteOwnedProfile($userSid)
                    $deleted=$lastProfileError -eq 0
                    if(-not $deleted){Start-Sleep -Milliseconds 200}
                }while(-not $deleted -and $profileWatch.Elapsed.TotalSeconds -lt 30)
                if(-not $deleted -or (Test-Path -LiteralPath $profileKey) -or (Test-Path -LiteralPath $profilePath)){throw "Disposable profile cleanup failed (Win32 $lastProfileError)."}
            }
            $result.profile_removed=$true
        }catch{$cleanupErrors.Add('profile: '+$_.Exception.Message)}
    }
    if($created){try{[SwirlDisposableUser.Native]::RemoveUser($userName);$result.account_removed=-not [SwirlDisposableUser.Native]::UserExists($userName)}catch{$cleanupErrors.Add('account: '+$_.Exception.Message)}}
    try {
        Assert-SwirlPathWithoutLinks $fixture
        Get-ChildItem -LiteralPath $fixture -Recurse -Force|ForEach-Object {Assert-SwirlPathWithoutLinks $_.FullName}
        Remove-Item -LiteralPath $fixture -Recurse -Force
        $result.fixture_removed=-not (Test-Path -LiteralPath $fixture)
    }catch{$cleanupErrors.Add('bootstrap-fixture: '+$_.Exception.Message)}
    $result.cleanup_errors=@($cleanupErrors.ToArray())
    if($cleanupErrors.Count -or -not $result.account_removed -or -not $result.profile_removed -or
        -not $result.desktop_access_removed -or -not $result.window_station_access_removed -or
        -not $result.desktop_dacl_restored -or -not $result.window_station_dacl_restored -or
        -not $result.input_acls_restored -or -not $result.fixture_removed){$result.success=$false}
    $result|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $evidence 'standard-user-runner.json') -Encoding UTF8
}
if(-not $result.success){throw ('Disposable standard-user acceptance failed: '+$result.error+' '+($cleanupErrors -join '; '))}
Write-Host 'Actual standard-user child, non-elevated medium token, profile and scoped cleanup verified.'
