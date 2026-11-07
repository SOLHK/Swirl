# Read-only, bounded, redacted diagnostics. Never use these observations to
# exempt a change from the installer's independent raw-fingerprint assertion.
# Native layouts: INTERNET_PER_CONN_OPTIONW / INTERNET_PER_CONN_OPTION_LISTW.
# https://learn.microsoft.com/windows/win32/api/wininet/ns-wininet-internet_per_conn_optionw
# https://learn.microsoft.com/windows/win32/api/winreg/nf-winreg-regqueryvalueexw
if (-not ('SwirlProxyDiagnostic.Native' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace SwirlProxyDiagnostic {
  public sealed class ValueDigest {
    public string name; public bool present; public uint? native_type, byte_length; public string sha256;
  }
  public sealed class KeyDigest {
    public string view, path; public bool present; public ValueDigest[] values;
  }
  public sealed class StringDigest {
    public bool is_null; public int utf16_code_units; public string sha256;
  }
  public sealed class QueryAttempt {
    public uint flags_option; public bool success; public int error; public uint option_error;
    public uint? flags, unknown_flag_bits; public StringDigest server, bypass, pac;
    public int option_bytes, list_bytes;
  }
  public static class Native {
    const string InternetKey = @"Software\Microsoft\Windows\CurrentVersion\Internet Settings";
    const int MaxBytes = 65536, MaxValues = 4096;
    static readonly IntPtr CurrentUser = new IntPtr(unchecked((int)0x80000001));
    static readonly string[] Known = {"ProxyEnable", "ProxyServer", "ProxyOverride", "AutoConfigURL", "AutoDetect"};
    [DllImport("advapi32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
    static extern int RegOpenKeyExW(IntPtr root, string path, int options, int access, out IntPtr key);
    [DllImport("advapi32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
    static extern int RegQueryValueExW(IntPtr key, string name, IntPtr reserved, out uint type, [Out] byte[] data, ref uint size);
    [DllImport("advapi32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
    static extern int RegEnumValueW(IntPtr key, uint index, StringBuilder name, ref uint chars, IntPtr reserved, IntPtr type, IntPtr data, IntPtr bytes);
    [DllImport("advapi32.dll", ExactSpelling=true)] static extern int RegCloseKey(IntPtr key);
    [DllImport("wininet.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    static extern bool InternetQueryOptionW(IntPtr internet, uint option, IntPtr buffer, ref uint length);
    [DllImport("kernel32.dll", ExactSpelling=true)] static extern IntPtr GlobalFree(IntPtr memory);

    public static string Digest(byte[] data) {
      using (SHA256 hash = SHA256.Create()) { return BitConverter.ToString(hash.ComputeHash(data)).Replace("-", "").ToLowerInvariant(); }
    }
    static void Check(int error, string operation) {
      if (error != 0) throw new InvalidOperationException(operation + " failed; native code " + error);
    }
    static string Name(string name, bool connections) {
      if (!connections || name == "DefaultConnectionSettings" || name == "SavedLegacySettings") return name;
      return "name-sha256:" + Digest(Encoding.Unicode.GetBytes(name));
    }
    static ValueDigest ReadValue(IntPtr key, string name, bool connections) {
      ValueDigest result = new ValueDigest { name=Name(name, connections) };
      for (int attempt=0; attempt<4; ++attempt) {
        uint type, size=0;
        int error=RegQueryValueExW(key, name, IntPtr.Zero, out type, null, ref size);
        if (error==2) return result;
        if (error!=234) Check(error, "Registry size query");
        if (size>MaxBytes) throw new InvalidOperationException("Registry diagnostic byte bound exceeded.");
        byte[] bytes=new byte[(int)size];
        try {
          error=RegQueryValueExW(key, name, IntPtr.Zero, out type, bytes, ref size);
          if (error==2) return result;
          if (error==234) continue;
          Check(error, "Registry value query");
          if (size>bytes.Length) throw new InvalidOperationException("Registry diagnostic read exceeded its buffer.");
          result.present=true; result.native_type=type; result.byte_length=size;
          using (SHA256 hash=SHA256.Create()) {
            result.sha256=BitConverter.ToString(hash.ComputeHash(bytes, 0, (int)size)).Replace("-", "").ToLowerInvariant();
          }
          return result;
        } finally { Array.Clear(bytes, 0, bytes.Length); }
      }
      throw new InvalidOperationException("Registry value changed repeatedly during diagnostic read.");
    }
    public static KeyDigest[] Registry() {
      List<KeyDigest> result=new List<KeyDigest>();
      foreach (int view in new int[] {0x200, 0x100}) {
        foreach (bool connections in new bool[] {false, true}) {
          KeyDigest item=new KeyDigest { view=view==0x200 ? "Registry32" : "Registry64", path=connections ? "Connections" : "InternetSettings" };
          List<ValueDigest> values=new List<ValueDigest>(); IntPtr key;
          int error=RegOpenKeyExW(CurrentUser, InternetKey+(connections ? @"\Connections" : ""), 0, 1|view, out key);
          if (error!=2 && error!=3) Check(error, "Registry key query");
          item.present=error==0;
          if (item.present) {
            try {
              if (!connections) { foreach (string name in Known) values.Add(ReadValue(key, name, false)); }
              else {
                for (uint index=0; ; ++index) {
                  uint chars=16384; StringBuilder name=new StringBuilder((int)chars);
                  error=RegEnumValueW(key, index, name, ref chars, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
                  if (error==259) break;
                  Check(error, "Registry value enumeration");
                  if (index>=MaxValues) throw new InvalidOperationException("Registry diagnostic value-count bound exceeded.");
                  values.Add(ReadValue(key, name.ToString(), true));
                }
              }
            } finally { Check(RegCloseKey(key), "Registry key close"); }
          } else if (!connections) {
            foreach (string name in Known) values.Add(new ValueDigest { name=name });
          }
          values.Sort((a,b) => StringComparer.Ordinal.Compare(a.name,b.name));
          item.values=values.ToArray(); result.Add(item);
        }
      }
      return result.ToArray();
    }
    static StringDigest StringValue(IntPtr address) {
      if (address==IntPtr.Zero) return new StringDigest { is_null=true };
      int chars=0;
      while (chars<32768 && Marshal.ReadInt16(address, checked(chars*2))!=0) ++chars;
      if (chars==32768) throw new InvalidOperationException("WinINet diagnostic string bound exceeded.");
      byte[] bytes=new byte[chars*2];
      try { Marshal.Copy(address,bytes,0,bytes.Length); return new StringDigest { utf16_code_units=chars, sha256=Digest(bytes) }; }
      finally { Array.Clear(bytes,0,bytes.Length); }
    }
    public static QueryAttempt Query(uint flagsOption) {
      if (flagsOption!=10 && flagsOption!=1) throw new ArgumentException("Unsupported diagnostic flags option.");
      // FILETIME in the option union is 8 bytes with 4-byte alignment on x86.
      // Explicit offsets avoid the CLR's differing Int64 alignment on x86.
      int optionBytes=IntPtr.Size==8 ? 16 : 12, valueOffset=IntPtr.Size==8 ? 8 : 4;
      int listBytes=IntPtr.Size==8 ? 32 : 20, countOffset=IntPtr.Size==8 ? 16 : 8;
      int optionsOffset=IntPtr.Size==8 ? 24 : 16;
      IntPtr options=IntPtr.Zero, list=IntPtr.Zero; bool optionsInitialized=false;
      QueryAttempt result=new QueryAttempt { flags_option=flagsOption, option_bytes=optionBytes, list_bytes=listBytes };
      try {
        options=Marshal.AllocHGlobal(optionBytes*4); Marshal.Copy(new byte[optionBytes*4],0,options,optionBytes*4); optionsInitialized=true;
        list=Marshal.AllocHGlobal(listBytes); Marshal.Copy(new byte[listBytes],0,list,listBytes);
        uint[] ids={flagsOption,2,3,4};
        for (int i=0;i<4;++i) Marshal.WriteInt32(options,i*optionBytes,unchecked((int)ids[i]));
        Marshal.WriteInt32(list,0,listBytes); Marshal.WriteInt32(list,countOffset,4); Marshal.WriteIntPtr(list,optionsOffset,options);
        uint length=(uint)listBytes;
        result.success=InternetQueryOptionW(IntPtr.Zero,75,list,ref length);
        result.error=result.success ? 0 : Marshal.GetLastWin32Error();
        result.option_error=unchecked((uint)Marshal.ReadInt32(list,countOffset+4));
        if (result.success) {
          if (length!=listBytes) throw new InvalidOperationException("WinINet diagnostic returned an unexpected list size.");
          uint flags=unchecked((uint)Marshal.ReadInt32(options,valueOffset));
          result.flags=flags; result.unknown_flag_bits=flags & ~15u;
          result.server=StringValue(Marshal.ReadIntPtr(options,optionBytes+valueOffset));
          result.bypass=StringValue(Marshal.ReadIntPtr(options,optionBytes*2+valueOffset));
          result.pac=StringValue(Marshal.ReadIntPtr(options,optionBytes*3+valueOffset));
        }
        return result;
      } finally {
        bool freed=true;
        if (options!=IntPtr.Zero) {
          HashSet<IntPtr> owned=new HashSet<IntPtr>();
          for (int i=1;optionsInitialized && i<4;++i) {
            IntPtr value=Marshal.ReadIntPtr(options,i*optionBytes+valueOffset);
            if (value!=IntPtr.Zero && owned.Add(value) && GlobalFree(value)!=IntPtr.Zero) freed=false;
          }
          Marshal.FreeHGlobal(options);
        }
        if (list!=IntPtr.Zero) Marshal.FreeHGlobal(list);
        if (!freed) throw new InvalidOperationException("WinINet diagnostic string cleanup failed.");
      }
    }
  }
}
'@
}

function Get-SwirlProxyRegistryDiagnostic {
    $keys=@([SwirlProxyDiagnostic.Native]::Registry())
    $json=ConvertTo-Json -InputObject $keys -Depth 6 -Compress
    return [pscustomobject][ordered]@{schema=1;process_bits=([IntPtr]::Size*8);keys=$keys;sha256=[SwirlProxyDiagnostic.Native]::Digest([Text.Encoding]::UTF8.GetBytes($json))}
}
function Compare-SwirlProxyRegistryDiagnostic([object]$Before,[object]$After) {
    # Compare every recorded field, not only the outer digest. Names outside
    # the public allowlist have already been replaced by hashes in native code.
    $maps=@(@{},@{});$snapshots=@($Before,$After)
    for($i=0;$i -lt 2;++$i) {
        foreach($key in $snapshots[$i].keys) {
            $prefix=$key.view+'/'+$key.path
            if($maps[$i].ContainsKey($prefix+'/key-present')){throw 'Duplicate key in proxy diagnostic snapshot.'}
            $maps[$i][$prefix+'/key-present']=$key.present
            foreach($value in $key.values) {
                $id=$prefix+'/'+$value.name
                if($maps[$i].ContainsKey($id+'/entry')){throw 'Duplicate value in proxy diagnostic snapshot.'}
                $maps[$i][$id+'/entry']=$true
                foreach($field in @('present','native_type','byte_length','sha256')){$maps[$i][$id+'/'+$field]=$value.$field}
            }
        }
    }
    $changes=New-Object 'System.Collections.Generic.List[object]'
    foreach($path in @(@($maps[0].Keys)+@($maps[1].Keys)|Sort-Object -Unique)) {
        $left=$maps[0].ContainsKey($path);$right=$maps[1].ContainsKey($path)
        if($left -ne $right -or ($maps[0][$path]|ConvertTo-Json -Compress) -cne ($maps[1][$path]|ConvertTo-Json -Compress)) {
            $changes.Add([ordered]@{path=$path;before_recorded=$left;after_recorded=$right;before=$maps[0][$path];after=$maps[1][$path]})
        }
    }
    return [ordered]@{equal=($changes.Count -eq 0);changes=@($changes.ToArray())}
}
function Get-SwirlProxyQueryDiagnostic([int]$ObserveDelayMilliseconds=0) {
    if($ObserveDelayMilliseconds -lt 0 -or $ObserveDelayMilliseconds -gt 500){throw 'Proxy observation delay is outside its bound.'}
    $before=Get-SwirlProxyRegistryDiagnostic
    $watch=[Diagnostics.Stopwatch]::StartNew()
    $attempts=New-Object 'System.Collections.Generic.List[object]'
    $attempt=[SwirlProxyDiagnostic.Native]::Query(10);$attempts.Add($attempt)
    if(-not $attempt.success){$attempt=[SwirlProxyDiagnostic.Native]::Query(1);$attempts.Add($attempt)}
    $watch.Stop()
    $after=Get-SwirlProxyRegistryDiagnostic
    $result=[ordered]@{raw_before=$before;query_success=$attempt.success;query_elapsed_ms=$watch.Elapsed.TotalMilliseconds;fallback_used=($attempts.Count -eq 2);attempts=@($attempts.ToArray());raw_after=$after;raw_difference=(Compare-SwirlProxyRegistryDiagnostic $before $after)}
    if($ObserveDelayMilliseconds -gt 0) {
        Start-Sleep -Milliseconds $ObserveDelayMilliseconds
        $settled=Get-SwirlProxyRegistryDiagnostic
        $result.observe_delay_ms=$ObserveDelayMilliseconds;$result.raw_after_delay=$settled
        $result.raw_difference_after_delay=Compare-SwirlProxyRegistryDiagnostic $before $settled
    }
    return $result
}
