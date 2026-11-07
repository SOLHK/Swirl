# Only the disposable-account wrapper calls this helper. It binds the freshly
# created profile before DeleteProfileW and never changes an ACL, service or hive.
# All native observations and deletion results remain in the caller's receipt.
if (-not ('SwirlOwnedProfileCleanup.Native' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;

namespace SwirlOwnedProfileCleanup {
  public sealed class Identity {
    public string relative_path,volume_serial,file_id,canonical_path_sha256;
    public bool directory; public uint attributes;
    internal string Full;
    internal bool Same(Identity other) {
      return other!=null && volume_serial==other.volume_serial && file_id==other.file_id &&
        String.Equals(Full,other.Full,StringComparison.OrdinalIgnoreCase) && directory==other.directory;
    }
  }
  public sealed class Scope {
    internal string Root,User,Sid;
    internal List<Identity> Ancestors;
    internal int Consumed;
    public Identity root_identity { get { return Ancestors[Ancestors.Count-1]; } }
    public int bound_ancestor_count { get { return Ancestors.Count; } }
    public string scope { get { return "Exact newly created account token path, bound before native profile deletion; not a general directory remover."; } }
  }
  public sealed class Deletion {
    public string relative_path,volume_serial,file_id;
    public bool disposition_accepted,handle_closed,namespace_absent;
    public int? win32_error;
  }
  public sealed class AdmissionAttempt {
    // elapsed_ms uses the one invocation's cumulative clock. retry_wait_ms is
    // the requested sleep; retry_wait_elapsed_ms records actual scheduling time.
    public int number,handles_opened,handles_closed,remaining_budget_ms,retry_wait_ms;
    public double started_elapsed_ms,elapsed_ms,retry_wait_started_elapsed_ms,retry_wait_elapsed_ms;
    public bool admission_complete,disposition_started,sharing_retry_eligible;
    public string error_operation;
    public int? win32_error;
    public List<string> errors=new List<string>();
  }
  public sealed class Result {
    public int schema=2;
    public bool success,admission_complete,disposition_started,root_absent,deadline_exceeded;
    public int initial_budget_ms,remaining_budget_ms,handles_opened,handles_closed;
    public double elapsed_ms;
    public string error_operation;
    public int? win32_error;
    public string scope="Only fixed WebCache remnants in this invocation's new disposable profile. All ancestors are handle-bound; no reparse traversal, ACL changes, service stops or hive operations.";
    public List<Identity> admitted_paths=new List<Identity>();
    public List<Deletion> deletions=new List<Deletion>();
    public List<string> errors=new List<string>();
    public List<AdmissionAttempt> admission_attempts=new List<AdmissionAttempt>();
  }
  public sealed class Control {
    public string name; public bool passed; public string error;
    public Result cleanup;
    public SharingControlEvidence sharing;
  }
  public sealed class SharingControlEvidence {
    public uint holder_access=0x10080,holder_share=7,cleanup_share=3;
    public bool holder_opened,sharing_observed,release_requested,release_after_observed_sharing,holder_closed,holder_thread_joined,held_through_cleanup_return;
    public int observed_attempt_number;
    public double observed_elapsed_ms;
    public int? open_error,close_error;
    public string thread_error,intervention;
  }
  public sealed class Controls {
    public int schema=1,total,passed; public bool success,fixture_removed;
    public string scope="Actual Win32 handle-bound deletion on newly created synthetic directories; no real accounts or user profiles. This does not establish installed-product cleanup.";
    public List<Control> cases=new List<Control>();
  }
  public static class Native {
    const uint ReadAttributes=0x80,DeleteAccess=0x10000,DirectoryAttribute=0x10,Reparse=0x400;
    const uint OpenExisting=3,OpenReparse=0x00200000,BackupSemantics=0x02000000;
    static readonly IntPtr Invalid=new IntPtr(-1);
    static readonly string[] AllowedDirectories={".","AppData","AppData/Local","AppData/Local/Microsoft","AppData/Local/Microsoft/Windows","AppData/Local/Microsoft/Windows/WebCache"};
    static readonly string[] AllowedFiles={
      "AppData/Local/Microsoft/Windows/WebCacheLock.dat",
      "AppData/Local/Microsoft/Windows/WebCache/V01.chk",
      "AppData/Local/Microsoft/Windows/WebCache/V01.log",
      "AppData/Local/Microsoft/Windows/WebCache/V01tmp.log",
      "AppData/Local/Microsoft/Windows/WebCache/WebCacheV01.dat",
      "AppData/Local/Microsoft/Windows/WebCache/WebCacheV01.jfm"};
    static readonly HashSet<string> DirectorySet=new HashSet<string>(AllowedDirectories,StringComparer.OrdinalIgnoreCase);
    static readonly HashSet<string> FileSet=new HashSet<string>(AllowedFiles,StringComparer.OrdinalIgnoreCase);
    [StructLayout(LayoutKind.Sequential)] struct FileId { public ulong Volume; public ulong Low,High; }
    [StructLayout(LayoutKind.Sequential)] struct AttributeTag { public uint Attributes,Tag; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true,ExactSpelling=true)]
    static extern IntPtr CreateFileW(string name,uint access,uint share,IntPtr security,uint disposition,uint flags,IntPtr template);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll",SetLastError=true,EntryPoint="GetFileInformationByHandleEx")]
    static extern bool FileIdentity(IntPtr handle,int kind,out FileId data,uint size);
    [DllImport("kernel32.dll",SetLastError=true,EntryPoint="GetFileInformationByHandleEx")]
    static extern bool ReadAttributeTag(IntPtr handle,int kind,out AttributeTag data,uint size);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true,ExactSpelling=true)]
    static extern uint GetFinalPathNameByHandleW(IntPtr handle,StringBuilder name,uint size,uint flags);
    [DllImport("kernel32.dll",SetLastError=true)]
    static extern bool SetFileInformationByHandle(IntPtr handle,int kind,byte[] data,uint size);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true,ExactSpelling=true)]
    static extern uint GetFileAttributesW(string name);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true,ExactSpelling=true)]
    [return: MarshalAs(UnmanagedType.U1)]
    static extern bool CreateSymbolicLinkW(string link,string target,uint flags);
    sealed class Opened { internal IntPtr Handle; internal Identity Identity; }
    sealed class Work {
      internal readonly Result Result=new Result();
      internal readonly Stopwatch Watch=Stopwatch.StartNew();
      internal readonly int Limit;
      internal Work(int limit) { Limit=limit;Result.initial_budget_ms=limit;Result.remaining_budget_ms=limit; }
      internal int RemainingMilliseconds { get { return (int)Math.Max(0,Math.Floor(Limit-Watch.Elapsed.TotalMilliseconds)); } }
      internal void Check(string operation) {
        Result.error_operation=operation;
        if(Limit<=0 || Watch.Elapsed.TotalMilliseconds>=Limit) {
          Result.deadline_exceeded=true;throw new InvalidOperationException("OriginalDeadlineExhausted");
        }
      }
    }
    static string Canonical(string path) {
      if(String.IsNullOrWhiteSpace(path)||path.Length>240||!Regex.IsMatch(path,@"^[A-Za-z]:\\"))
        throw new InvalidOperationException("LocalAbsolutePathRequired");
      string full=Path.GetFullPath(path);
      if(full.Substring(2).IndexOf(':')>=0||full.IndexOfAny(new char[]{'\0','*','?'})>=0)
        throw new InvalidOperationException("AmbiguousPath");
      return full.Length==3 ? full : full.TrimEnd('\\');
    }
    static string Digest(string value) {
      using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(value.Replace('\\','/').ToLowerInvariant()))).Replace("-","").ToLowerInvariant();
    }
    static string NativePath(IntPtr handle) {
      var name=new StringBuilder(32768);uint count=GetFinalPathNameByHandleW(handle,name,(uint)name.Capacity,0);
      if(count==0)throw new Win32Exception(Marshal.GetLastWin32Error());
      if(count>=name.Capacity)throw new InvalidOperationException("FinalPathTooLong");
      string value=name.ToString();
      if(value.StartsWith(@"\\?\",StringComparison.Ordinal))value=value.Substring(4);
      return Canonical(value);
    }
    static Opened Open(string full,string relative,bool directory,bool deletion,Work work) {
      work.Check("open:"+relative);
      IntPtr handle=CreateFileW(full,ReadAttributes|(deletion?DeleteAccess:0),3,IntPtr.Zero,OpenExisting,OpenReparse|BackupSemantics,IntPtr.Zero);
      if(handle==Invalid)throw new Win32Exception(Marshal.GetLastWin32Error());
      work.Result.handles_opened++;
      var opened=new Opened {Handle=handle};
      try {
        AttributeTag attributes;FileId id;
        if(Marshal.SizeOf(typeof(AttributeTag))!=8||Marshal.SizeOf(typeof(FileId))!=24)
          throw new InvalidOperationException("FileIdentityAbiMismatch");
        if(!ReadAttributeTag(handle,9,out attributes,8))throw new Win32Exception(Marshal.GetLastWin32Error());
        if((attributes.Attributes&Reparse)!=0||((attributes.Attributes&DirectoryAttribute)!=0)!=directory)
          throw new InvalidOperationException("ReparseOrKindMismatch");
        if(!FileIdentity(handle,18,out id,24))throw new Win32Exception(Marshal.GetLastWin32Error());
        if(id.Low==0&&id.High==0)throw new InvalidOperationException("EmptyFileIdentity");
        string actual=NativePath(handle);
        if(!String.Equals(actual,Canonical(full),StringComparison.OrdinalIgnoreCase))
          throw new InvalidOperationException("FinalPathMismatch");
        opened.Identity=new Identity {Full=actual,relative_path=relative,directory=directory,attributes=attributes.Attributes,
          volume_serial=id.Volume.ToString("x16",CultureInfo.InvariantCulture),
          file_id=id.High.ToString("x16",CultureInfo.InvariantCulture)+id.Low.ToString("x16",CultureInfo.InvariantCulture),canonical_path_sha256=Digest(actual)};
        work.Check("identity:"+relative);return opened;
      }catch {Release(opened,work);throw;}
    }
    static bool Release(Opened opened,Work work) {
      if(opened==null||opened.Handle==IntPtr.Zero)return true;
      bool ok=CloseHandle(opened.Handle);opened.Handle=IntPtr.Zero;
      if(ok)work.Result.handles_closed++;
      else work.Result.errors.Add("HandleCloseFailed:"+Marshal.GetLastWin32Error().ToString(CultureInfo.InvariantCulture));
      return ok;
    }
    static List<string> AncestorPaths(string root) {
      var paths=new List<string>();DirectoryInfo next=new DirectoryInfo(root);
      while(next!=null) { if(paths.Count>=24)throw new InvalidOperationException("AncestorLimit");paths.Add(Canonical(next.FullName));next=next.Parent; }
      paths.Reverse();return paths;
    }
    public static Scope BindBeforeNativeDelete(string root,string user,string sid,int remainingMilliseconds) {
      if(!Regex.IsMatch(user??"",@"\Aswci_[0-9a-f]{12}\z")||String.IsNullOrWhiteSpace(sid)||!new SecurityIdentifier(sid).IsAccountSid())
        throw new InvalidOperationException("FreshAccountIdentityRequired");
      root=Canonical(root);
      if(!String.Equals(Path.GetFileName(root),user,StringComparison.Ordinal))
        throw new InvalidOperationException("ExactTokenProfileNameRequired");
      var work=new Work(Math.Min(remainingMilliseconds,30000));var identities=new List<Identity>();
      foreach(string path in AncestorPaths(root)) {
        var opened=Open(path,String.Equals(path,root,StringComparison.OrdinalIgnoreCase)?".":"ancestor-"+identities.Count.ToString(CultureInfo.InvariantCulture),true,false,work);
        try {identities.Add(opened.Identity);}finally {Release(opened,work);}
      }
      work.Check("bind-complete");
      if(work.Result.errors.Count!=0||work.Result.handles_opened!=work.Result.handles_closed)
        throw new InvalidOperationException("BindingHandleClosureUnconfirmed");
      return new Scope {Root=root,User=user,Sid=sid,Ancestors=identities};
    }
    static bool Absent(string path) {
      uint attributes=GetFileAttributesW(path);
      if(attributes!=UInt32.MaxValue)return false;
      int error=Marshal.GetLastWin32Error();
      if(error==2||error==3)return true;
      throw new Win32Exception(error);
    }
    static int Depth(string relative) { return relative=="."?0:relative.Split('/').Length; }
    public static Result DeleteFixedResiduals(Scope scope,int remainingMilliseconds) {
      return DeleteCore(scope,remainingMilliseconds,null,null);
    }
    public static bool RootAbsentAfterCleanup(Scope scope) {
      if(scope==null)throw new InvalidOperationException("BoundProfileScopeRequired");
      return Absent(scope.Root); // Access denial and other errors are not absence.
    }
    static string FailureCode(Exception error) {
      return error is Win32Exception?"Win32OperationFailed":error is InvalidOperationException?error.Message:error.GetType().Name;
    }
    static void Fail(Work work,Exception error,string operation) {
      var native=error as Win32Exception;
      work.Result.error_operation=operation;
      work.Result.win32_error=native==null?(int?)null:native.NativeErrorCode;
      work.Result.errors.Add(FailureCode(error));
    }
    static List<Opened> TryAdmission(Scope scope,Work work,List<Opened> opened) {
      // Every attempt begins at the original bound ancestor identities. Holding
      // them without delete sharing prevents replacement during this attempt.
      foreach(var original in scope.Ancestors) {
        var entry=Open(original.Full,original.relative_path,true,String.Equals(original.Full,scope.Root,StringComparison.OrdinalIgnoreCase),work);opened.Add(entry);
        if(!original.Same(entry.Identity))throw new InvalidOperationException("PreDeleteAncestorIdentityChanged");
      }
      var owned=new List<Opened>();owned.Add(opened[opened.Count-1]);
      var pending=new Queue<Opened>();pending.Enqueue(owned[0]);
      var seen=new HashSet<string>(StringComparer.OrdinalIgnoreCase);seen.Add(".");
      while(pending.Count!=0) {
        var parent=pending.Dequeue();work.Check("enumerate:"+parent.Identity.relative_path);
        foreach(string child in Directory.EnumerateFileSystemEntries(parent.Identity.Full)) {
          work.Check("admit-entry");
          string relative=parent.Identity.relative_path=="."?Path.GetFileName(child):parent.Identity.relative_path+"/"+Path.GetFileName(child);
          bool directory=DirectorySet.Contains(relative),file=FileSet.Contains(relative);
          if((!directory&&!file)||!seen.Add(relative)||seen.Count>12)
            throw new InvalidOperationException("UnknownDuplicateOrExcessResidual");
          var entry=Open(child,relative,directory,true,work);opened.Add(entry);owned.Add(entry);
          if(entry.Identity.volume_serial!=scope.root_identity.volume_serial)
            throw new InvalidOperationException("ResidualVolumeChanged");
          if(directory)pending.Enqueue(entry);
        }
      }
      return owned;
    }
    static void DeleteAdmitted(Scope scope,Work work,List<Opened> owned,Action admittedControl) {
      foreach(var entry in owned)work.Result.admitted_paths.Add(entry.Identity);
      work.Result.admission_complete=true;
      if(admittedControl!=null)admittedControl(); // Internal actual-file race control only.
      owned.Sort((a,b)=> {int order=Depth(b.Identity.relative_path).CompareTo(Depth(a.Identity.relative_path));
        return order!=0?order:String.Compare(a.Identity.relative_path,b.Identity.relative_path,StringComparison.Ordinal);});
      foreach(var entry in owned) {
        work.Check("delete:"+entry.Identity.relative_path);
        // The one-byte BOOLEAN is FILE_DISPOSITION_INFO, not a four-byte BOOL.
        // No POSIX disposition, readonly override, or recursive shell deletion.
        var deletion=new Deletion {relative_path=entry.Identity.relative_path,volume_serial=entry.Identity.volume_serial,file_id=entry.Identity.file_id};
        work.Result.deletions.Add(deletion);work.Result.disposition_started=true;
        deletion.disposition_accepted=SetFileInformationByHandle(entry.Handle,4,new byte[]{1},1);
        if(!deletion.disposition_accepted) {deletion.win32_error=Marshal.GetLastWin32Error();throw new Win32Exception(deletion.win32_error.Value);}
        deletion.handle_closed=Release(entry,work);
        if(!deletion.handle_closed)throw new InvalidOperationException("DeletionHandleCloseFailed");
        work.Check("confirm-absent:"+entry.Identity.relative_path);
        deletion.namespace_absent=Absent(entry.Identity.Full);
        if(!deletion.namespace_absent)throw new InvalidOperationException("DeletedPathRemainsOrRecreated");
      }
      work.Result.root_absent=Absent(scope.Root);work.Check("final-absence");
      if(!work.Result.root_absent)throw new InvalidOperationException("ProfileRootRemains");
      work.Result.error_operation=null;work.Result.win32_error=null;
    }
    static Result DeleteCore(Scope scope,int remainingMilliseconds,Action admittedControl,Action<AdmissionAttempt> retryControl) {
      var work=new Work(Math.Min(remainingMilliseconds,30000));
      try {
        work.Check("admission");
        if(scope==null||Interlocked.Exchange(ref scope.Consumed,1)!=0)
          throw new InvalidOperationException("ScopeMissingOrAlreadyConsumed");
        while(true) {
          // Neither the consumed scope nor its original clock is recreated.
          // All admission collections are new; no partial traversal survives.
          var opened=new List<Opened>();Exception failure=null;
          int openedBefore=work.Result.handles_opened,closedBefore=work.Result.handles_closed,errorsBefore=work.Result.errors.Count;
          var attempt=new AdmissionAttempt {number=work.Result.admission_attempts.Count+1,started_elapsed_ms=work.Watch.Elapsed.TotalMilliseconds};
          try {DeleteAdmitted(scope,work,TryAdmission(scope,work,opened),admittedControl);}
          catch(Exception error) {failure=error;attempt.error_operation=work.Result.error_operation;var native=error as Win32Exception;attempt.win32_error=native==null?(int?)null:native.NativeErrorCode;attempt.errors.Add(FailureCode(error));}
          finally {
            for(int index=opened.Count-1;index>=0;index--)Release(opened[index],work);
            for(int index=errorsBefore;index<work.Result.errors.Count;index++)attempt.errors.Add(work.Result.errors[index]);
            attempt.handles_opened=work.Result.handles_opened-openedBefore;attempt.handles_closed=work.Result.handles_closed-closedBefore;
            attempt.admission_complete=work.Result.admission_complete;attempt.disposition_started=work.Result.disposition_started;
            attempt.elapsed_ms=work.Watch.Elapsed.TotalMilliseconds;attempt.remaining_budget_ms=work.RemainingMilliseconds;
            work.Result.admission_attempts.Add(attempt);
          }
          var sharing=failure as Win32Exception;
          attempt.sharing_retry_eligible=sharing!=null&&sharing.NativeErrorCode==32&&attempt.errors.Count==1&&
            work.Result.errors.Count==0&&!work.Result.admission_complete&&!work.Result.disposition_started&&work.Result.deletions.Count==0&&
            attempt.handles_opened==attempt.handles_closed&&work.Result.handles_opened==work.Result.handles_closed&&
            !work.Result.deadline_exceeded&&attempt.remaining_budget_ms>0;
          if(!attempt.sharing_retry_eligible) {if(failure!=null)Fail(work,failure,attempt.error_operation);break;}
          if(retryControl!=null)retryControl(attempt); // Internal signalled native-holder controls only.
          work.Check("sharing-retry-budget");
          int delay=Math.Min(200,work.RemainingMilliseconds);
          if(delay<=0) {Fail(work,failure,attempt.error_operation);break;}
          attempt.retry_wait_ms=delay;attempt.retry_wait_started_elapsed_ms=work.Watch.Elapsed.TotalMilliseconds;
          Thread.Sleep(delay);attempt.retry_wait_elapsed_ms=work.Watch.Elapsed.TotalMilliseconds-attempt.retry_wait_started_elapsed_ms;
          if(work.RemainingMilliseconds==0) {
            Fail(work,failure,attempt.error_operation);
            if(work.Watch.Elapsed.TotalMilliseconds>=work.Limit) {work.Result.deadline_exceeded=true;work.Result.errors.Add("OriginalDeadlineExhausted");}
            break;
          }
        }
      }catch(Exception error) {Fail(work,error,work.Result.error_operation);}
      finally {
        work.Result.elapsed_ms=work.Watch.Elapsed.TotalMilliseconds;work.Result.remaining_budget_ms=work.RemainingMilliseconds;
        if(work.Result.elapsed_ms>=work.Limit)work.Result.deadline_exceeded=true;
        work.Result.success=work.Result.errors.Count==0&&work.Result.admission_complete&&work.Result.root_absent&&
          !work.Result.deadline_exceeded&&work.Result.handles_opened==work.Result.handles_closed;
      }
      return work.Result;
    }
    static string MakeFixture(string parent,bool all) {
      string root=Path.Combine(parent,"swci_"+Guid.NewGuid().ToString("N").Substring(0,12));Directory.CreateDirectory(root);
      foreach(string name in all?AllowedFiles:new[]{AllowedFiles[0]}) {
        string full=Path.Combine(root,name.Replace('/',Path.DirectorySeparatorChar));Directory.CreateDirectory(Path.GetDirectoryName(full));File.WriteAllText(full,"synthetic fixture");
      }
      return root;
    }
    static Scope FixtureScope(string root) {return BindBeforeNativeDelete(root,Path.GetFileName(root),"S-1-5-21-1-2-3-1001",30000);}
    static void Check(bool value,string code) {if(!value)throw new InvalidOperationException(code);}
    static void RemoveFixture(string root) {
      if(!Directory.Exists(root))return;
      foreach(string entry in Directory.EnumerateFileSystemEntries(root)) {
        FileAttributes attributes=File.GetAttributes(entry);
        if((attributes&FileAttributes.Directory)!=0) {
          if((attributes&FileAttributes.ReparsePoint)!=0)Directory.Delete(entry);else RemoveFixture(entry);
        }else {File.SetAttributes(entry,FileAttributes.Normal);File.Delete(entry);}
      }
      Directory.Delete(root);
    }
    // These controls use a separate real handle with DELETE access and share 7.
    // Its DELETE access conflicts with the cleanup's unchanged share 3 even
    // though the holder permits all sharing. Release is signalled only after
    // the cleanup has actually observed error 32 and closed its entire attempt.
    sealed class HeldDeleteControl : IDisposable {
      internal readonly SharingControlEvidence Evidence=new SharingControlEvidence();
      readonly ManualResetEvent ready=new ManualResetEvent(false),release=new ManualResetEvent(false),closed=new ManualResetEvent(false);
      readonly Thread thread;bool started,disposed;
      internal HeldDeleteControl(string file) {
        thread=new Thread(()=> {
          IntPtr held=Invalid;
          try {
            held=CreateFileW(file,ReadAttributes|DeleteAccess,7,IntPtr.Zero,OpenExisting,OpenReparse|BackupSemantics,IntPtr.Zero);
            if(held==Invalid) {Evidence.open_error=Marshal.GetLastWin32Error();return;}
            Evidence.holder_opened=true;ready.Set();
            if(!release.WaitOne(5000))Evidence.thread_error="HolderReleaseSignalDeadline";
          }catch(Exception error) {Evidence.thread_error=FailureCode(error);}
          finally {
            ready.Set();
            if(held!=Invalid) {
              Evidence.holder_closed=CloseHandle(held);
              if(!Evidence.holder_closed)Evidence.close_error=Marshal.GetLastWin32Error();
            }
            closed.Set();
          }
        });
        thread.IsBackground=true;
      }
      internal void Start() {
        thread.Start();started=true;
        Check(ready.WaitOne(5000),"HolderOpenSignalDeadline");
        Check(Evidence.holder_opened&&!Evidence.open_error.HasValue,"HolderOpenFailed");
        Check(IsHeld,"HolderExitedBeforeCleanup");
      }
      internal bool IsHeld { get {return Evidence.holder_opened&&!closed.WaitOne(0);} }
      internal void ReleaseAfterSharing(AdmissionAttempt attempt) {
        Check(IsHeld&&!Evidence.release_requested,"HolderReleasedBeforeNativeSharingViolation");
        Check(attempt.win32_error==32&&attempt.error_operation=="open:"+AllowedFiles[0]&&attempt.errors.Count==1&&
          !attempt.admission_complete&&!attempt.disposition_started&&attempt.handles_opened==attempt.handles_closed&&attempt.sharing_retry_eligible,
          "NativeSharingBoundaryNotObserved");
        Evidence.sharing_observed=true;Evidence.observed_attempt_number=attempt.number;Evidence.observed_elapsed_ms=attempt.elapsed_ms;
        Evidence.release_after_observed_sharing=true;Evidence.release_requested=true;release.Set();
        Check(closed.WaitOne(Math.Min(1000,attempt.remaining_budget_ms)),"HolderCloseSignalDeadline");
        Check(Evidence.holder_closed&&!Evidence.close_error.HasValue&&Evidence.thread_error==null,"HolderCloseUnconfirmed");
      }
      public void Dispose() {
        if(disposed)return;
        // Always request release, including a failed admission/control. Do not
        // dispose events under an unjoined thread or call a close a success.
        Evidence.release_requested=true;release.Set();
        Evidence.holder_thread_joined=!started||thread.Join(5000);
        if(!Evidence.holder_thread_joined)throw new InvalidOperationException("HolderThreadExitUnconfirmed");
        ready.Dispose();release.Dispose();closed.Dispose();disposed=true;
        Check(!Evidence.holder_opened||Evidence.holder_closed,"HolderCloseUnconfirmed");
        Check(Evidence.thread_error==null&&!Evidence.open_error.HasValue&&!Evidence.close_error.HasValue,"HolderNativeControlFailed");
      }
    }
    static void CheckSharingHistory(Result result,int budget) {
      Check(result.initial_budget_ms==budget&&result.admission_attempts.Count>=2,"SharingRetryNotExercised");
      var first=result.admission_attempts[0];
      Check(first.win32_error==32&&first.error_operation=="open:"+AllowedFiles[0]&&first.errors.Count==1&&
        !first.admission_complete&&!first.disposition_started&&first.handles_opened==first.handles_closed&&
        first.sharing_retry_eligible&&first.retry_wait_ms>0&&first.retry_wait_ms<=200,"FirstSharingAttemptEvidenceMissing");
      double previous=0;
      foreach(var attempt in result.admission_attempts) {
        Check(attempt.started_elapsed_ms>=previous&&attempt.elapsed_ms>=attempt.started_elapsed_ms&&
          attempt.remaining_budget_ms>=0&&attempt.remaining_budget_ms<=budget&&attempt.retry_wait_ms<=200&&
          attempt.retry_wait_ms<=attempt.remaining_budget_ms&&attempt.handles_opened==attempt.handles_closed,"SharingRetryClockOrClosureChanged");
        previous=attempt.elapsed_ms+attempt.retry_wait_elapsed_ms;
      }
      Check(result.handles_opened==result.handles_closed,"SharingRetryLeakedHandles");
    }
    static bool SharingOrOriginalDeadline(Result result) {
      foreach(string error in result.errors)if(error!="Win32OperationFailed"&&error!="OriginalDeadlineExhausted")return false;
      return result.win32_error==32||(result.deadline_exceeded&&result.errors.Contains("OriginalDeadlineExhausted"));
    }
    static void Case(Controls report,string name,Action action) {
      Case(report,name,item=>action());
    }
    static void Case(Controls report,string name,Action<Control> action) {
      var item=new Control {name=name};report.cases.Add(item);report.total++;
      try {action(item);item.passed=true;report.passed++;}catch(Exception error) {item.error=error.GetType().Name+":"+(error is Win32Exception?((Win32Exception)error).NativeErrorCode.ToString(CultureInfo.InvariantCulture):error.Message);}
    }
    public static Controls RunNativeControls(string fixtureRoot) {
      fixtureRoot=Canonical(fixtureRoot);
      if(Directory.Exists(fixtureRoot)||File.Exists(fixtureRoot))throw new InvalidOperationException("ControlFixtureAlreadyExists");
      Directory.CreateDirectory(fixtureRoot);var report=new Controls();
      try {
        Case(report,"all-six-files-and-ancestors",()=> {string root=MakeFixture(fixtureRoot,true);var scope=FixtureScope(root);var r=DeleteFixedResiduals(scope,30000);Check(r.success&&r.deletions.Count==12&&RootAbsentAfterCleanup(scope)&&r.handles_opened==r.handles_closed,"CompleteCleanupFailed");Directory.CreateDirectory(root);Check(!RootAbsentAfterCleanup(scope),"LateRootRecreationIgnored");});
        Case(report,"known-subset-and-single-use-scope",()=> {string root=MakeFixture(fixtureRoot,false);var scope=FixtureScope(root);var r=DeleteFixedResiduals(scope,30000);var second=DeleteFixedResiduals(scope,30000);Check(r.success&&r.deletions.Count==6&&!second.success&&second.handles_opened==0&&second.errors.Contains("ScopeMissingOrAlreadyConsumed"),"ScopeReuseAccepted");});
        Case(report,"unknown-file-rejects-before-any-delete",()=> {string root=MakeFixture(fixtureRoot,true);string unknown=Path.Combine(root,"keep.txt");File.WriteAllText(unknown,"owned negative");var r=DeleteFixedResiduals(FixtureScope(root),30000);Check(!r.success&&!r.admission_complete&&r.deletions.Count==0&&r.errors.Contains("UnknownDuplicateOrExcessResidual")&&File.Exists(unknown)&&File.Exists(Path.Combine(root,AllowedFiles[0])),"UnknownFileTouched");});
        Case(report,"prebound-root-replacement",()=> {string root=MakeFixture(fixtureRoot,true);var scope=FixtureScope(root);Directory.Move(root,root+"-original");Directory.CreateDirectory(root);File.WriteAllText(Path.Combine(root,"keep.txt"),"owned replacement");var r=DeleteFixedResiduals(scope,30000);Check(!r.success&&!r.admission_complete&&r.deletions.Count==0&&r.errors.Contains("PreDeleteAncestorIdentityChanged")&&File.Exists(Path.Combine(root,"keep.txt")),"ReplacementAccepted");});
        Case(report,"deadline-before-start",()=> {string root=MakeFixture(fixtureRoot,true);var r=DeleteFixedResiduals(FixtureScope(root),0);Check(!r.success&&r.deadline_exceeded&&r.handles_opened==0&&r.errors.Contains("OriginalDeadlineExhausted")&&File.Exists(Path.Combine(root,AllowedFiles[0])),"ExpiredAdmissionAccepted");});
        Case(report,"held-file-rejects-before-deletion",()=> {string root=MakeFixture(fixtureRoot,true);var scope=FixtureScope(root);using(var held=new FileStream(Path.Combine(root,AllowedFiles[0]),FileMode.Open,FileAccess.Read,FileShare.None)) {var r=DeleteFixedResiduals(scope,200);Check(!r.success&&!r.admission_complete&&!r.disposition_started&&r.deletions.Count==0&&r.admission_attempts.Count>0&&r.admission_attempts[0].win32_error==32&&SharingOrOriginalDeadline(r)&&r.handles_opened==r.handles_closed,"HeldFileAccepted");}});
        Case(report,"readonly-is-not-overridden",()=> {string root=MakeFixture(fixtureRoot,false);string file=Path.Combine(root,AllowedFiles[0]);File.SetAttributes(file,File.GetAttributes(file)|FileAttributes.ReadOnly);var r=DeleteFixedResiduals(FixtureScope(root),30000);Check(!r.success&&r.admission_complete&&r.deletions.Count==1&&!r.deletions[0].disposition_accepted&&r.deletions[0].win32_error==5&&r.win32_error==5&&r.handles_opened==r.handles_closed&&File.Exists(file)&&(File.GetAttributes(file)&FileAttributes.ReadOnly)!=0,"ReadonlyOverride");});
        Case(report,"late-unknown-residual-keeps-failure",()=> {string root=MakeFixture(fixtureRoot,true);string extra=Path.Combine(root,"AppData","Local","Microsoft","Windows","WebCache","late.txt");var r=DeleteCore(FixtureScope(root),30000,()=>File.WriteAllText(extra,"owned race"),null);Check(!r.success&&r.admission_complete&&r.win32_error==145&&File.Exists(extra)&&!r.root_absent,"RecreatedEntryIgnored");});
        Case(report,"reparse-child-target-is-untouched",()=> {string root=MakeFixture(fixtureRoot,false);string app=Path.Combine(root,"AppData");RemoveFixture(app);string outside=Path.Combine(fixtureRoot,"owned-link-target");Directory.CreateDirectory(outside);string marker=Path.Combine(outside,"keep.txt");File.WriteAllText(marker,"owned target");if(!CreateSymbolicLinkW(app,outside,3))throw new Win32Exception(Marshal.GetLastWin32Error());var r=DeleteFixedResiduals(FixtureScope(root),30000);Check(!r.success&&!r.admission_complete&&r.deletions.Count==0&&r.errors.Contains("ReparseOrKindMismatch")&&File.ReadAllText(marker)=="owned target","ReparseTraversed");});
        Case(report,"wrong-profile-name-cannot-bind",()=> {string root=MakeFixture(fixtureRoot,true);bool rejected=false;try {BindBeforeNativeDelete(root,"swci_000000000000","S-1-5-21-1-2-3-1001",30000);}catch(InvalidOperationException error){rejected=error.Message=="ExactTokenProfileNameRequired";}Check(rejected&&Directory.Exists(root),"WrongProfileBound");});
        Case(report,"ancestor-reparse-cannot-bind",()=> {string target=Path.Combine(fixtureRoot,"owned-ancestor-target");Directory.CreateDirectory(target);string root=MakeFixture(target,true);string alias=Path.Combine(fixtureRoot,"owned-ancestor-link");if(!CreateSymbolicLinkW(alias,target,3))throw new Win32Exception(Marshal.GetLastWin32Error());bool rejected=false;try {FixtureScope(Path.Combine(alias,Path.GetFileName(root)));}catch(InvalidOperationException error){rejected=error.Message=="ReparseOrKindMismatch";}Check(rejected&&File.Exists(Path.Combine(root,AllowedFiles[0])),"AncestorReparseBound");});
        Case(report,"delete-pending-is-not-complete",()=> {string root=MakeFixture(fixtureRoot,false);var scope=FixtureScope(root);using(var held=new FileStream(Path.Combine(root,AllowedFiles[0]),FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete)) {var r=DeleteFixedResiduals(scope,30000);Check(!r.success&&r.admission_complete&&r.deletions.Count>0&&r.deletions[0].disposition_accepted&&r.deletions[0].handle_closed&&!r.root_absent&&Directory.Exists(root),"PendingDeleteAcceptedAsComplete");}});
        Case(report,"delete-access-share7-released-after-native32",item=> {
          string root=MakeFixture(fixtureRoot,true);var scope=FixtureScope(root);
          using(var holder=new HeldDeleteControl(Path.Combine(root,AllowedFiles[0]))) {
            item.sharing=holder.Evidence;holder.Start();
            item.cleanup=DeleteCore(scope,3000,null,attempt=>holder.ReleaseAfterSharing(attempt));
            CheckSharingHistory(item.cleanup,3000);
            Check(item.cleanup.success&&item.cleanup.admission_complete&&item.cleanup.disposition_started&&item.cleanup.deletions.Count==12&&
              item.cleanup.errors.Count==0&&!item.cleanup.win32_error.HasValue&&item.cleanup.elapsed_ms<3000&&RootAbsentAfterCleanup(scope)&&
              item.sharing.sharing_observed&&item.sharing.release_after_observed_sharing&&item.sharing.holder_closed,"ReleasedSharingCleanupFailed");
            var reused=DeleteFixedResiduals(scope,3000);
            Check(!reused.success&&reused.handles_opened==0&&reused.errors.Contains("ScopeMissingOrAlreadyConsumed"),"SharingRetryReusedExternalScope");
          }
          Check(item.sharing.holder_thread_joined,"ReleasedHolderThreadNotJoined");
        });
        Case(report,"delete-access-share7-held-through-original-deadline",item=> {
          string root=MakeFixture(fixtureRoot,true);var scope=FixtureScope(root);
          using(var holder=new HeldDeleteControl(Path.Combine(root,AllowedFiles[0]))) {
            item.sharing=holder.Evidence;holder.Start();item.cleanup=DeleteFixedResiduals(scope,750);
            item.sharing.held_through_cleanup_return=holder.IsHeld&&!item.sharing.release_requested;
            CheckSharingHistory(item.cleanup,750);
            Check(!item.cleanup.success&&!item.cleanup.admission_complete&&!item.cleanup.disposition_started&&item.cleanup.deletions.Count==0&&
              SharingOrOriginalDeadline(item.cleanup)&&item.cleanup.remaining_budget_ms==0&&item.cleanup.elapsed_ms>=749&&
              item.sharing.held_through_cleanup_return&&File.Exists(Path.Combine(root,AllowedFiles[0])),"PersistentSharingWasAccepted");
            foreach(var attempt in item.cleanup.admission_attempts) {
              bool terminalDeadline=attempt.number==item.cleanup.admission_attempts.Count&&item.cleanup.deadline_exceeded&&
                !attempt.win32_error.HasValue&&attempt.errors.Count==1&&attempt.errors[0]=="OriginalDeadlineExhausted";
              bool onlySharing=attempt.win32_error==32&&attempt.errors.Count==1&&attempt.errors[0]=="Win32OperationFailed";
              Check((onlySharing||terminalDeadline)&&!attempt.admission_complete&&!attempt.disposition_started,"PersistentSharingFailureChanged");
            }
          }
          Check(item.sharing.holder_closed&&item.sharing.holder_thread_joined,"PersistentHolderReleaseUnconfirmed");
        });
        Case(report,"sharing-retry-rechecks-original-root-identity",item=> {
          string root=MakeFixture(fixtureRoot,true);var scope=FixtureScope(root);string original=root+"-original";
          using(var holder=new HeldDeleteControl(Path.Combine(root,AllowedFiles[0]))) {
            item.sharing=holder.Evidence;holder.Start();
            item.cleanup=DeleteCore(scope,3000,null,attempt=> {
              holder.ReleaseAfterSharing(attempt);Directory.Move(root,original);Directory.CreateDirectory(root);
              File.WriteAllText(Path.Combine(root,"keep.txt"),"owned replacement");item.sharing.intervention="root-replaced-after-closed-sharing-attempt";
            });
            CheckSharingHistory(item.cleanup,3000);
            Check(!item.cleanup.success&&!item.cleanup.admission_complete&&!item.cleanup.disposition_started&&item.cleanup.deletions.Count==0&&
              item.cleanup.errors.Contains("PreDeleteAncestorIdentityChanged")&&item.cleanup.admission_attempts.Count==2&&
              File.Exists(Path.Combine(root,"keep.txt"))&&File.Exists(Path.Combine(original,AllowedFiles[0])),"RetryAcceptedReplacementRoot");
          }
          Check(item.sharing.holder_closed&&item.sharing.holder_thread_joined,"ReplacementHolderReleaseUnconfirmed");
        });
        Case(report,"sharing-retry-reenumerates-and-rejects-unknown",item=> {
          string root=MakeFixture(fixtureRoot,true);var scope=FixtureScope(root);string unknown=Path.Combine(root,"keep.txt");
          using(var holder=new HeldDeleteControl(Path.Combine(root,AllowedFiles[0]))) {
            item.sharing=holder.Evidence;holder.Start();
            item.cleanup=DeleteCore(scope,3000,null,attempt=> {
              holder.ReleaseAfterSharing(attempt);File.WriteAllText(unknown,"owned new entry");item.sharing.intervention="unknown-created-after-closed-sharing-attempt";
            });
            CheckSharingHistory(item.cleanup,3000);
            Check(!item.cleanup.success&&!item.cleanup.admission_complete&&!item.cleanup.disposition_started&&item.cleanup.deletions.Count==0&&
              item.cleanup.errors.Contains("UnknownDuplicateOrExcessResidual")&&item.cleanup.admission_attempts.Count==2&&
              File.Exists(unknown)&&File.Exists(Path.Combine(root,AllowedFiles[0])),"RetryMissedUnknownEntry");
          }
          Check(item.sharing.holder_closed&&item.sharing.holder_thread_joined,"UnknownEntryHolderReleaseUnconfirmed");
        });
      }finally {RemoveFixture(fixtureRoot);report.fixture_removed=Absent(fixtureRoot);report.success=report.total==report.passed&&report.fixture_removed;}
      return report;
    }
  }
}
'@
}
