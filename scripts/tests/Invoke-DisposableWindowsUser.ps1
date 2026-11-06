param(
    [Parameter(Mandatory=$true)][string]$Script,
    [Parameter(Mandatory=$true)][string]$ArgumentsFile,
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory,
    [ValidateRange(30,1800)][int]$TimeoutSeconds=600,
    [ValidateSet('x86','x64')][string]$PowerShellArchitecture='x86'
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$PowerShellArchitecture=$PowerShellArchitecture.ToLowerInvariant()
$expected64BitProcess=$PowerShellArchitecture -ceq 'x64'
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
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
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
    [DllImport("userenv.dll",CharSet=CharSet.Unicode,ExactSpelling=true,SetLastError=true)]
    [return: MarshalAs(UnmanagedType.Bool)] static extern bool DeleteProfileW(string sid,string profile,string computer);
    public sealed class ProfileDeleteResult { public bool Succeeded; public int Error; }
    static ProfileDeleteResult DeleteProfileResult(string sid,string profile) {
      bool succeeded=DeleteProfileW(sid,profile,null);
      int error=succeeded ? 0 : Marshal.GetLastWin32Error();
      return new ProfileDeleteResult { Succeeded=succeeded, Error=error };
    }
    public static ProfileDeleteResult DeleteOwnedProfile(string sid) {
      // https://learn.microsoft.com/windows/win32/api/userenv/nf-userenv-deleteprofilew
      // PowerShell converts $null passed to a string parameter to "". The
      // computer argument must be a native NULL on supported Windows versions.
      // Preserve BOOL separately: FALSE with error 0 is not a successful call.
      return DeleteProfileResult(sid,null);
    }
    public static ProfileDeleteResult DeleteOwnedProfileAtVerifiedPath(string sid,string profile) {
      // The caller admits only its exact token-verified, unlinked temporary
      // profile after the registry-resolved call succeeded and both hives left.
      if(String.IsNullOrWhiteSpace(profile)||!Path.IsPathRooted(profile))throw new ArgumentException("A verified absolute profile path is required.");
      return DeleteProfileResult(sid,profile);
    }
    public sealed class ProfileInventoryEntry {
      public string relative_path,kind,attribute_names,error_operation,error_message;
      public int depth; public int? attributes,hresult; public long? bytes;
    }
    public sealed class ProfileInventory {
      public int entry_limit=128,depth_limit=12; public bool truncated;
      public string[] truncation_reasons; public ProfileInventoryEntry[] entries;
    }
    sealed class ProfileInventoryPath { public string Full,Relative; public int Depth; }
    public static ProfileInventory ReadOwnedProfileInventory(string root) {
      // Metadata only. Lazy enumeration, bounded queue and no recursion through
      // observed reparse points; do not read file contents or resolve link targets.
      var result=new ProfileInventory();var entries=new List<ProfileInventoryEntry>();
      var limits=new List<string>();var pending=new Queue<ProfileInventoryPath>();
      pending.Enqueue(new ProfileInventoryPath { Full=Path.GetFullPath(root),Relative=".",Depth=0 });
      while(pending.Count!=0) {
        var path=pending.Dequeue();var entry=new ProfileInventoryEntry { relative_path=path.Relative,depth=path.Depth,kind="unknown" };
        entries.Add(entry);string operation="attributes";
        try {
          FileAttributes attributes=File.GetAttributes(path.Full);
          entry.attributes=(int)attributes;entry.attribute_names=attributes.ToString();
          if((attributes&FileAttributes.ReparsePoint)!=0){entry.kind="reparse-point-not-followed";continue;}
          if((attributes&FileAttributes.Directory)==0){entry.kind="file";operation="file-size";entry.bytes=new FileInfo(path.Full).Length;continue;}
          entry.kind="directory";
          if(path.Depth>=result.depth_limit){result.truncated=true;if(!limits.Contains("depth-limit"))limits.Add("depth-limit");continue;}
          operation="directory-enumeration";
          foreach(string child in Directory.EnumerateFileSystemEntries(path.Full)) {
            if(entries.Count+pending.Count>=result.entry_limit){result.truncated=true;if(!limits.Contains("entry-limit"))limits.Add("entry-limit");break;}
            pending.Enqueue(new ProfileInventoryPath { Full=child,Relative=(path.Relative=="." ? "" : path.Relative+"/")+Path.GetFileName(child),Depth=path.Depth+1 });
          }
        }catch(Exception error){
          entry.error_operation=operation;entry.hresult=error.HResult;
          entry.error_message="Profile metadata observation failed; no file contents were read.";
          if(error is FileNotFoundException||error is DirectoryNotFoundException)entry.kind="missing";
        }
      }
      result.entries=entries.ToArray();result.truncation_reasons=limits.ToArray();return result;
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
    powershell_architecture=$PowerShellArchitecture;expected_64_bit_process=$expected64BitProcess;actual_64_bit_process=$null
    profile_loaded=$false;child_completed=$false;remaining_job_processes=$null;forced_termination=$false
    account_removed=$false;profile_removed=$false;desktop_access_removed=$false;window_station_access_removed=$false
    desktop_dacl_restored=$false;window_station_dacl_restored=$false
    input_acls_restored=$false;input_acl_checks=@();fixture_removed=$false;error=$null;cleanup_errors=@();profile_cleanup=$null;profile_owner_diagnostics=$null}
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
        $config=[ordered]@{script=$targetScript;parameters=$parameters;evidence=$evidence;expectedSid=$userSid;parentSid=$parentIdentity.User.Value;expected64BitProcess=$expected64BitProcess}
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
    if($receipt.sid -cne $data.expectedSid -or $receipt.sid -ceq $data.parentSid -or $receipt.is_admin -or ($receipt.is_64_bit_process -ne $data.expected64BitProcess)){throw 'Expected actual standard-user Windows PowerShell process with the requested architecture.'}
    if(-not $receipt.profile -or $env:USERPROFILE -ine $receipt.profile){throw 'Actual user profile/environment did not load.'}
    $parameters=@{};foreach($property in $data.parameters.PSObject.Properties){$parameters[$property.Name]=$property.Value}
    & $data.script @parameters *> (Join-Path $data.evidence 'standard-user-output.log')
    $receipt.success=$true
} catch {$receipt.error=$_.Exception.Message;[IO.File]::WriteAllText((Join-Path $data.evidence 'standard-user-error.log'),($_|Out-String))}
finally {$receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $data.evidence 'standard-user-child.json') -Encoding UTF8}
if(-not $receipt.success){exit 1}
'@
        [IO.File]::WriteAllText($bootstrap,$bootstrapText,(New-Object Text.UTF8Encoding $true))
        $powershellRelative=if($expected64BitProcess){'System32\WindowsPowerShell\v1.0\powershell.exe'}else{'SysWOW64\WindowsPowerShell\v1.0\powershell.exe'}
        $powershell=Join-Path $env:WINDIR $powershellRelative
        if(-not (Test-Path -LiteralPath $powershell -PathType Leaf)){throw 'The requested architecture of Windows PowerShell 5.1 is unavailable.'}
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
    $result.actual_64_bit_process=$receipt.is_64_bit_process
    if(-not $receipt.success -or $receipt.sid -cne $userSid -or $receipt.is_admin -or ($receipt.is_64_bit_process -ne $expected64BitProcess)){throw 'The actual child identity, architecture or result is invalid.'}
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
        $profileAttempts=New-Object 'System.Collections.Generic.List[object]'
        $profileObservations=New-Object 'System.Collections.Generic.List[object]'
        $result.profile_cleanup=[ordered]@{deadline_ms=30000;poll_interval_ms=200;path_scope='Exact newly created disposable account; raw profile paths omitted from observations.';path_verified=$false;token_path_verified=$false;native_delete_accepted=$false;explicit_path_delete_attempted=$false;attempts=$profileAttempts;observations=$profileObservations;inventory_before=$null;inventory_after_registry_delete=$null;inventory_final=$null;final_state=$null;elapsed_ms=$null}
        try {
            $profileKey='Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\'+$userSid
            $tokenProfilePath=if($null -ne $result.token){[string]$result.token.ProfilePath}else{$null}
            $profilePath=$tokenProfilePath
            if(Test-Path -LiteralPath $profileKey){
                $registeredPath=[Environment]::ExpandEnvironmentVariables((Get-ItemProperty -LiteralPath $profileKey).ProfileImagePath)
                if($profilePath -and [IO.Path]::GetFullPath($profilePath) -ine [IO.Path]::GetFullPath($registeredPath)){throw 'Disposable profile registry path differs from the verified child token.'}
                $profilePath=$registeredPath
            }
            if($profilePath){
                Assert-SwirlPathWithoutLinks $profilePath
                if($profilePath -ieq [Environment]::GetFolderPath('UserProfile') -or [IO.Path]::GetFileName($profilePath) -notlike ($userName+'*')){throw 'Refusing a profile outside the newly created account.'}
                $result.profile_cleanup.path_verified=$true
                $result.profile_cleanup.token_path_verified=-not [string]::IsNullOrWhiteSpace($tokenProfilePath)
                $profileWatch=[Diagnostics.Stopwatch]::StartNew()
                function Read-OwnedProfileCleanupState {
                    $observation=[ordered]@{
                        elapsed_ms=$null
                        profile_key_exists=(Test-Path -LiteralPath $profileKey)
                        profile_path_exists=(Test-Path -LiteralPath $profilePath)
                        user_hive_loaded=(Test-Path -LiteralPath ('Registry::HKEY_USERS\'+$userSid))
                        user_classes_hive_loaded=(Test-Path -LiteralPath ('Registry::HKEY_USERS\'+$userSid+'_Classes'))
                    }
                    $observation.elapsed_ms=$profileWatch.Elapsed.TotalMilliseconds
                    return $observation
                }
                try {
                    $result.profile_cleanup.inventory_before=[SwirlDisposableUser.Native]::ReadOwnedProfileInventory($profilePath)
                    while($true) {
                        $state=Read-OwnedProfileCleanupState
                        $profileObservations.Add($state);$result.profile_cleanup.final_state=$state
                        if($state.elapsed_ms -le 30000 -and -not $state.profile_key_exists -and -not $state.profile_path_exists -and -not $state.user_hive_loaded -and -not $state.user_classes_hive_loaded){$result.profile_removed=$true;break}
                        if($profileWatch.ElapsedMilliseconds -ge 30000){break}
                        # The native NULL profile path is resolved from ProfileList.
                        # Retry only a still-registered profile after a failed BOOL.
                        # After acceptance, do not repeat the registry-resolved
                        # call; observe cleanup, with one verified explicit-path
                        # retry below if only the owned directory remains.
                        if($state.profile_key_exists -and -not $result.profile_cleanup.native_delete_accepted) {
                            $attempt=[ordered]@{number=($profileAttempts.Count+1);path_mode='registry-resolved-null';before=$state;native_succeeded=$null;native_error=$null;after=$null}
                            $profileAttempts.Add($attempt)
                            $native=[SwirlDisposableUser.Native]::DeleteOwnedProfile($userSid)
                            $attempt.native_succeeded=$native.Succeeded;$attempt.native_error=$native.Error
                            if($native.Succeeded){
                                $result.profile_cleanup.native_delete_accepted=$true
                                $result.profile_cleanup.inventory_after_registry_delete=[SwirlDisposableUser.Native]::ReadOwnedProfileInventory($profilePath)
                            }
                            $attempt.after=Read-OwnedProfileCleanupState
                            $state=$attempt.after;$result.profile_cleanup.final_state=$state
                            if($attempt.after.elapsed_ms -le 30000 -and -not $attempt.after.profile_key_exists -and -not $attempt.after.profile_path_exists -and -not $attempt.after.user_hive_loaded -and -not $attempt.after.user_classes_hive_loaded){$result.profile_removed=$true;break}
                        }
                        if($profileWatch.ElapsedMilliseconds -lt 30000 -and $result.profile_cleanup.native_delete_accepted -and $result.profile_cleanup.token_path_verified -and
                           -not $result.profile_cleanup.explicit_path_delete_attempted -and $state.profile_path_exists -and
                           -not $state.profile_key_exists -and -not $state.user_hive_loaded -and -not $state.user_classes_hive_loaded) {
                            # Once ProfileList is gone, a NULL-path retry cannot
                            # resolve the directory. Admit one documented native
                            # profile deletion with the previously verified path.
                            # No direct filesystem deletion or hive unload.
                            Assert-SwirlPathWithoutLinks $tokenProfilePath
                            $result.profile_cleanup.explicit_path_delete_attempted=$true
                            $attempt=[ordered]@{number=($profileAttempts.Count+1);path_mode='explicit-verified-token-path';before=$state;native_succeeded=$null;native_error=$null;after=$null}
                            $profileAttempts.Add($attempt)
                            $native=[SwirlDisposableUser.Native]::DeleteOwnedProfileAtVerifiedPath($userSid,$tokenProfilePath)
                            $attempt.native_succeeded=$native.Succeeded;$attempt.native_error=$native.Error
                            $attempt.after=Read-OwnedProfileCleanupState
                            $result.profile_cleanup.final_state=$attempt.after
                            if($attempt.after.elapsed_ms -le 30000 -and -not $attempt.after.profile_key_exists -and -not $attempt.after.profile_path_exists -and -not $attempt.after.user_hive_loaded -and -not $attempt.after.user_classes_hive_loaded){$result.profile_removed=$true;break}
                        }
                        $remaining=30000-$profileWatch.ElapsedMilliseconds
                        if($remaining -le 0){break}
                        Start-Sleep -Milliseconds ([int][Math]::Min(200,$remaining))
                    }
                }finally{
                    # A service can recreate a directory after an earlier
                    # absence observation. Final metadata must not contradict
                    # a success flag, or receive extra time after the deadline.
                    $previouslyAbsent=$result.profile_removed
                    $result.profile_removed=$false
                    try {
                        $result.profile_cleanup.inventory_final=[SwirlDisposableUser.Native]::ReadOwnedProfileInventory($profilePath)
                        $finalState=Read-OwnedProfileCleanupState
                        $result.profile_cleanup.final_state=$finalState
                        $result.profile_removed=$previouslyAbsent -and $finalState.elapsed_ms -le 30000 -and
                            -not $finalState.profile_key_exists -and -not $finalState.profile_path_exists -and
                            -not $finalState.user_hive_loaded -and -not $finalState.user_classes_hive_loaded
                    }finally{
                        $profileWatch.Stop();$result.profile_cleanup.elapsed_ms=$profileWatch.Elapsed.TotalMilliseconds
                    }
                }
                if(-not $result.profile_removed){throw 'Disposable profile key, directory and both user hives were not confirmed absent within 30000 ms; see profile_cleanup.'}
            }else{
                if($result.profile_loaded -or (Test-Path -LiteralPath $profileKey) -or (Test-Path -LiteralPath ('Registry::HKEY_USERS\'+$userSid)) -or (Test-Path -LiteralPath ('Registry::HKEY_USERS\'+$userSid+'_Classes'))){throw 'The owned profile path is unavailable; cleanup cannot be verified.'}
                $result.profile_removed=$true
            }
        }catch{$cleanupErrors.Add('profile: '+$_.Exception.Message)}
    }
    if($created -and $null -ne $result.profile_cleanup -and -not $result.profile_removed){
        # Freeze the unchanged 30-second profile decision before querying.
        # Observe before account deletion can change external owner lifetimes.
        # This never retries deletion, unloads hives or changes acceptance flags.
        $ownerDiagnostic=[ordered]@{schema=1;scope='Post-failure evidence only; original acceptance remains failed.'
            attempted=$false;status='not-admitted';frozen_request_sha256=$null
            launcher_exit_code=$null;report_file=$null;report_sha256=$null;observation_success=$false;session_end_confirmed=$false;error=$null}
        $result.profile_owner_diagnostics=$ownerDiagnostic
        try {
            $cleanup=$result.profile_cleanup
            if(-not $cleanup.path_verified -or -not $cleanup.token_path_verified -or
               $cleanup.deadline_ms -ne 30000 -or $null -eq $cleanup.elapsed_ms -or $cleanup.elapsed_ms -lt 30000 -or
               $null -eq $cleanup.final_state -or -not $cleanup.final_state.profile_path_exists -or
               $cleanup.final_state.profile_key_exists -or $cleanup.final_state.user_hive_loaded -or $cleanup.final_state.user_classes_hive_loaded -or
               $null -eq $cleanup.inventory_final -or $PSVersionTable.PSVersion.Major -ne 7 -or
               [string]::IsNullOrWhiteSpace($env:SWIRL_PROFILE_OWNER_PYTHON) -or $env:GITHUB_SHA -cnotmatch '^[0-9a-f]{40}$'){
                throw 'OwnerDiagnosticFrozenFailureUnavailable'
            }
            $ownerFiles=@($cleanup.inventory_final.entries|Where-Object {$_.kind -ceq 'file' -and $null -eq $_.hresult -and $null -ne $_.attributes -and -not ($_.attributes -band 0x410)})
            if($ownerFiles.Count -lt 1 -or $ownerFiles.Count -gt 32){throw 'OwnerDiagnosticFileLimit'}
            $ownerDirectory=Join-Path $evidence 'profile-owner-diagnostics'
            Assert-SwirlPathWithoutLinks $ownerDirectory
            if(Test-Path -LiteralPath $ownerDirectory){throw 'OwnerDiagnosticOutputAlreadyExists'}
            [IO.Directory]::CreateDirectory($ownerDirectory)|Out-Null
            $ownerRequest=Join-Path $ownerDirectory 'frozen-cleanup.json'
            [ordered]@{schema=1;source_sha=$env:GITHUB_SHA;new_account_created=$created;username=$userName;sid=$userSid
                profile_removed=$result.profile_removed;frozen_scope='Profile cleanup at its original deadline; account and fixture cleanup are still pending.'
                profile_path=$profilePath;token_profile_path=$tokenProfilePath;path_verified=$cleanup.path_verified;token_path_verified=$cleanup.token_path_verified
                cleanup_deadline_ms=[int]$cleanup.deadline_ms;cleanup_elapsed_ms=$cleanup.elapsed_ms;final_state=$cleanup.final_state
                files=$ownerFiles;original_cleanup=$cleanup}|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $ownerRequest -Encoding UTF8
            $ownerDiagnostic.frozen_request_sha256=(Get-FileHash -LiteralPath $ownerRequest -Algorithm SHA256).Hash.ToLowerInvariant()
            $ownerLauncher=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../tools/ObserveWindowsProfileResidualOwners.py'))
            $ownerPowerShell=Join-Path $PSHOME 'pwsh.exe'
            foreach($ownerPath in @($env:SWIRL_PROFILE_OWNER_PYTHON,$ownerLauncher,$ownerPowerShell)){
                if($ownerPath -notmatch '^[A-Za-z]:\\' -or $ownerPath.Substring(2) -match '[/:<>"|?*\x00-\x1f]'){throw 'OwnerDiagnosticLocalPathRequired'}
                Assert-SwirlPathWithoutLinks $ownerPath
                if(-not [IO.File]::Exists($ownerPath)){throw 'OwnerDiagnosticExecutableUnavailable'}
            }
            $ownerDiagnostic.attempted=$true
            try {
                & $env:SWIRL_PROFILE_OWNER_PYTHON $ownerLauncher --request $ownerRequest --request-sha256 $ownerDiagnostic.frozen_request_sha256 --powershell $ownerPowerShell > (Join-Path $ownerDirectory 'launcher-stdout.log') 2> (Join-Path $ownerDirectory 'launcher-stderr.log')
            }finally{$ownerDiagnostic.launcher_exit_code=$LASTEXITCODE}
            $ownerReport=Join-Path $ownerDirectory 'owner-diagnostics.json'
            Assert-SwirlPathWithoutLinks $ownerReport
            if(-not [IO.File]::Exists($ownerReport) -or (New-Object IO.FileInfo $ownerReport).Length -gt 262144){throw 'OwnerDiagnosticReceiptUnavailable'}
            $ownerReceipt=Get-Content -LiteralPath $ownerReport -Raw -Encoding UTF8|ConvertFrom-Json
            if($ownerReceipt.schema -ne 1 -or $ownerReceipt.source_sha -cne $env:GITHUB_SHA -or
               $ownerReceipt.frozen_request_sha256 -cne $ownerDiagnostic.frozen_request_sha256 -or
               $ownerReceipt.original_profile_removed -ne $false -or $ownerReceipt.original_cleanup_deadline_ms -ne 30000){throw 'OwnerDiagnosticReceiptIdentityInvalid'}
            $ownerDiagnostic.status=[string]$ownerReceipt.status
            $ownerDiagnostic.report_file='profile-owner-diagnostics/owner-diagnostics.json'
            $ownerDiagnostic.report_sha256=(Get-FileHash -LiteralPath $ownerReport -Algorithm SHA256).Hash.ToLowerInvariant()
            $ownerDiagnostic.observation_success=$ownerReceipt.success -eq $true -and $ownerDiagnostic.launcher_exit_code -eq 0
            $ownerDiagnostic.session_end_confirmed=$ownerReceipt.session_end_confirmed -eq $true
        }catch{
            $ownerDiagnostic.error=if($_.Exception.Message -cmatch '^OwnerDiagnostic[A-Za-z]+$'){$_.Exception.Message}else{'OwnerDiagnosticObservationUnavailable'}
            $ownerDiagnostic.status='incomplete'
        }
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
