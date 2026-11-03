# Test-only real shortcut creation shared by the early x86 standard-user gate
# and the ordinary installer lifecycle. The actual WScript.Shell fixture lost
# Chinese description characters in the saved bytes. Use the native Unicode
# shell interface for both writing and reading, with exact .NET file staging.
if(-not ('SwirlIntegration.Tests.UnicodeShortcut' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

namespace SwirlIntegration.Tests {
    // Exact IUnknown method order and wide string signatures from Microsoft's
    // WinSDK ShObjIdl_core.h, win32metadata blob
    // 72edc050ff1277e6b4392eddbe86cd4d16560f8b. Void COM methods translate a
    // failing HRESULT to an exception; none of these methods uses PreserveSig.
    [ComImport]
    [Guid("000214F9-0000-0000-C000-000000000046")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IShellLinkW {
        void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path, int count, IntPtr findData, uint flags);
        void GetIDList(out IntPtr itemList);
        void SetIDList(IntPtr itemList);
        void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder description, int count);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string description);
        void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder directory, int count);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string directory);
        void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder arguments, int count);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string arguments);
        void GetHotkey(out ushort hotkey);
        void SetHotkey(ushort hotkey);
        void GetShowCmd(out int command);
        void SetShowCmd(int command);
        void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder iconPath, int count, out int iconIndex);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string iconPath, int iconIndex);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string relativePath, uint reserved);
        void Resolve(IntPtr window, uint flags);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string path);
    }

    // COM-imported construction lets the CLR initialize COM for this calling
    // thread; do not assume the host initialized it before a native P/Invoke.
    [ComImport]
    [Guid("00021401-0000-0000-C000-000000000046")]
    [ClassInterface(ClassInterfaceType.None)]
    internal class ShellLink { }

    public sealed class ShortcutObservation {
        public string TargetPath;
        public string Arguments;
        public string Description;
    }

    public static class UnicodeShortcut {
        private static object Create() {
            return new ShellLink();
        }

        public static void Write(string path, string target, string arguments, string description) {
            object instance = Create();
            try {
                IShellLinkW link = (IShellLinkW)instance;
                link.SetPath(target);
                link.SetArguments(arguments);
                link.SetDescription(description);
                // The Framework IPersistFile declaration uses LPWStr and BOOL.
                ((IPersistFile)instance).Save(path, true);
            } finally { Marshal.FinalReleaseComObject(instance); }
        }

        public static ShortcutObservation Read(string path) {
            object instance = Create();
            try {
                ((IPersistFile)instance).Load(path, 0); // STGM_READ; never Resolve.
                IShellLinkW link = (IShellLinkW)instance;
                StringBuilder target = new StringBuilder(32768);
                StringBuilder arguments = new StringBuilder(32768);
                StringBuilder description = new StringBuilder(32768);
                link.GetPath(target, target.Capacity, IntPtr.Zero, 4); // SLGP_RAWPATH
                link.GetArguments(arguments, arguments.Capacity);
                link.GetDescription(description, description.Capacity);
                return new ShortcutObservation {
                    TargetPath = target.ToString(), Arguments = arguments.ToString(),
                    Description = description.ToString()
                };
            } finally { Marshal.FinalReleaseComObject(instance); }
        }
    }
}
'@
}
function Save-SwirlTestShortcut {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Description
    )
    $destination=Assert-SwirlIntegrationPath ([IO.Path]::GetFullPath($Path))
    if([IO.Path]::GetExtension($destination) -ine '.lnk'){throw 'The shortcut fixture requires a .lnk destination.'}
    $target=Join-Path $PSHOME 'powershell.exe'
    $stage=Join-Path ([IO.Path]::GetTempPath()) ('swirl-shortcut-fixture-'+[guid]::NewGuid().ToString('N'))
    $null=Assert-SwirlIntegrationPath $stage
    if(Test-Path -LiteralPath $stage){throw 'The unique shortcut staging directory already exists.'}
    $null=[IO.Directory]::CreateDirectory($stage)
    $staged=Join-Path $stage 'Swirl.lnk'
    $readback=Join-Path $stage 'Readback.lnk'
    $failure=$null
    $expectedUnits=[ordered]@{target=@($target.ToCharArray()|ForEach-Object {[int]$_});arguments=@('-NoProfile'.ToCharArray()|ForEach-Object {[int]$_});description=@($Description.ToCharArray()|ForEach-Object {[int]$_})}
    $result=[ordered]@{api='IShellLinkW/IPersistFile';path=$destination;target=$target;arguments='-NoProfile';description=$Description;expected_utf16_code_units=$expectedUnits;observed_target=$null;observed_arguments=$null;observed_description=$null;observed_utf16_code_units=$null;target_matches=$false;arguments_match=$false;description_matches=$false;final_bytes_match=$false;stage_sha256=$null;stage_length=0;sha256=$null;length=0;bytes_base64=$null;staging_removed=$false;success=$false;error=$null}
    try {
        [SwirlIntegration.Tests.UnicodeShortcut]::Write($staged,$target,'-NoProfile',$Description)
        [byte[]]$expected=[IO.File]::ReadAllBytes($staged)
        $result.stage_sha256=Get-SwirlIntegrationHash $staged;$result.stage_length=$expected.Length
        if($expected.Length -eq 0 -or $expected.Length -gt 262144){throw 'The real shortcut fixture has an invalid size.'}
        Write-SwirlIntegrationFile $destination $expected
        # Read the actual final Unicode filename, not the original staged file.
        # Inspect a separate copy of these final bytes through the same native
        # Unicode interface; semantic metadata must come from the final file.
        [byte[]]$actual=[IO.File]::ReadAllBytes($destination)
        $result.sha256=Get-SwirlIntegrationHash $destination
        $result.length=$actual.Length;$result.bytes_base64=[Convert]::ToBase64String($actual)
        $result.final_bytes_match=[Convert]::ToBase64String($actual) -ceq [Convert]::ToBase64String($expected)
        if(-not $result.final_bytes_match){throw 'The final Unicode shortcut bytes differ from the staged shortcut.'}
        [IO.File]::WriteAllBytes($readback,$actual)
        $observed=[SwirlIntegration.Tests.UnicodeShortcut]::Read($readback)
        $result.observed_target=[string]$observed.TargetPath
        $result.observed_arguments=[string]$observed.Arguments
        $result.observed_description=[string]$observed.Description
        $result.observed_utf16_code_units=[ordered]@{target=@($result.observed_target.ToCharArray()|ForEach-Object {[int]$_});arguments=@($result.observed_arguments.ToCharArray()|ForEach-Object {[int]$_});description=@($result.observed_description.ToCharArray()|ForEach-Object {[int]$_})}
        $result.target_matches=[IO.Path]::GetFullPath($result.observed_target) -ieq [IO.Path]::GetFullPath($target)
        $result.arguments_match=$result.observed_arguments -ceq $result.arguments
        $result.description_matches=$result.observed_description -ceq $Description
        if(-not $result.target_matches -or -not $result.arguments_match -or -not $result.description_matches){throw 'The final Unicode shortcut target, arguments or exact description did not round-trip.'}
        $result.success=$true
    }catch{$failure=$_.Exception.Message}
    finally {
        try {
            $null=Assert-SwirlIntegrationPath $stage
            foreach($file in @($staged,$readback)){$null=Assert-SwirlIntegrationPath $file;if([IO.File]::Exists($file)){[IO.File]::Delete($file)}}
            [IO.Directory]::Delete($stage,$false)
            $result.staging_removed=-not [IO.Directory]::Exists($stage)
        }catch{$failure=([string]$failure+'; shortcut staging cleanup: '+$_.Exception.Message)}
    }
    # Keep partial native observations on a failed exact assertion. Both callers
    # still reject success=false; diagnostics must not erase the failing field.
    if($failure -or -not $result.staging_removed){$result.success=$false;$result.error=if($failure){$failure}else{'Shortcut staging cleanup was incomplete.'}}
    return [pscustomobject]$result
}
