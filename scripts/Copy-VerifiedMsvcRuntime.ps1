param(
    [string]$BuildDirectory,
    [string]$ApplicationDirectory
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'RustProductPackagePolicy.ps1')
$script:SwirlMsvcNamePattern='^(?:msvcp[0-9][a-z0-9_]*|vcruntime[0-9][a-z0-9_]*|concrt[0-9][a-z0-9_]*|vccorlib[0-9][a-z0-9_]*)\.dll$'
$script:SwirlMsvcCoreModules=@('msvcp140.dll','msvcp140_1.dll','msvcp140_2.dll','vcruntime140.dll','vcruntime140_1.dll')
if(-not ('SwirlMsvcPackage.PeImage' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
namespace SwirlMsvcPackage {
    public sealed class PeInfo {
        public string Machine;
        public string[] Imports;
        public string[] DelayImports;
    }
    public static class PeImage {
        private static void Bound(byte[] b, long p, long n) {
            if(p<0 || n<0 || p+n>b.LongLength) throw new InvalidDataException("PE range exceeds the file.");
        }
        private static UInt16 U16(byte[] b,long p){Bound(b,p,2);return BitConverter.ToUInt16(b,(int)p);}
        private static UInt32 U32(byte[] b,long p){Bound(b,p,4);return BitConverter.ToUInt32(b,(int)p);}
        private static UInt64 U64(byte[] b,long p){Bound(b,p,8);return BitConverter.ToUInt64(b,(int)p);}
        private sealed class Section {public UInt32 Address,Span,Raw,Size;}
        private static long Offset(byte[] b,List<Section> s,UInt32 headers,UInt64 rva,int length) {
            if(rva<headers){Bound(b,(long)rva,length);return (long)rva;}
            foreach(Section x in s) if(rva>=x.Address && rva<(UInt64)x.Address+x.Span) {
                UInt64 relative=rva-x.Address;
                if(relative+(UInt64)length>x.Size) throw new InvalidDataException("PE import points outside raw section data.");
                long at=(long)((UInt64)x.Raw+relative);Bound(b,at,length);return at;
            }
            throw new InvalidDataException("PE import RVA is not mapped.");
        }
        private static string Name(byte[] b,List<Section> s,UInt32 headers,UInt64 rva) {
            int at=(int)Offset(b,s,headers,rva,1),end=at;
            while(end<b.Length && end-at<4096 && b[end]!=0){if(b[end]>127)throw new InvalidDataException("Non-ASCII PE import name.");++end;}
            if(end==b.Length || end-at>=4096 || end==at)throw new InvalidDataException("Invalid PE import name.");
            string name=Encoding.ASCII.GetString(b,at,end-at);
            if(name.IndexOfAny(new char[]{'/', '\\', ':'})>=0)throw new InvalidDataException("Path-shaped PE import name.");
            return name;
        }
        public static PeInfo Read(string path) {
            long length=new FileInfo(path).Length;
            if(length<64 || length>536870912)throw new InvalidDataException("PE image exceeds its size bound.");
            byte[] b=File.ReadAllBytes(path);
            if(b[0]!='M'||b[1]!='Z')throw new InvalidDataException("Missing DOS header.");
            long pe=U32(b,60);Bound(b,pe,24);
            if(U32(b,pe)!=0x00004550)throw new InvalidDataException("Missing PE signature.");
            UInt16 machine=U16(b,pe+4),count=U16(b,pe+6),optionalSize=U16(b,pe+20);
            long optional=pe+24;Bound(b,optional,optionalSize);
            UInt16 magic=U16(b,optional);
            int directoryBase,numberOffset;UInt64 imageBase;
            if(magic==0x20b){directoryBase=112;numberOffset=108;imageBase=U64(b,optional+24);}
            else if(magic==0x10b){directoryBase=96;numberOffset=92;imageBase=U32(b,optional+28);}
            else throw new InvalidDataException("Unsupported PE optional header.");
            if(optionalSize<directoryBase || count==0 || count>96)throw new InvalidDataException("Invalid PE header bounds.");
            UInt32 headers=U32(b,optional+60),directories=U32(b,optional+numberOffset);
            if(directories>(optionalSize-directoryBase)/8)throw new InvalidDataException("PE data directories exceed optional header.");
            List<Section> sections=new List<Section>();
            for(int i=0;i<count;++i){long at=optional+optionalSize+40*i;Bound(b,at,40);
                sections.Add(new Section{Address=U32(b,at+12),Span=Math.Max(U32(b,at+8),U32(b,at+16)),Raw=U32(b,at+20),Size=U32(b,at+16)});}
            List<string> imports=new List<string>(),delayed=new List<string>();
            foreach(int index in new int[]{1,13}){
                if(index>=directories)continue;
                UInt32 rva=U32(b,optional+directoryBase+8*index);if(rva==0)continue;
                int stride=index==1?20:32;bool terminated=false;
                for(int i=0;i<4096;++i){long at=Offset(b,sections,headers,(UInt64)rva+(UInt64)(i*stride),stride);bool empty=true;
                    for(int n=0;n<stride;n+=4)if(U32(b,at+n)!=0)empty=false;
                    if(empty){terminated=true;break;}
                    UInt64 name;
                    if(index==1){name=U32(b,at+12);imports.Add(Name(b,sections,headers,name));}
                    else {name=U32(b,at+4);if((U32(b,at)&1)==0){if(name<imageBase)throw new InvalidDataException("Invalid delay import VA.");name-=imageBase;}
                        delayed.Add(Name(b,sections,headers,name));}
                }
                if(!terminated)throw new InvalidDataException("PE import descriptors exceed bound.");
            }
            return new PeInfo{Machine="0x"+machine.ToString("x4"),Imports=imports.ToArray(),DelayImports=delayed.ToArray()};
        }
    }
}
'@
}
function Get-SwirlMsvcHash([string]$Path) {
    $stream=[IO.File]::OpenRead($Path);$hash=[Security.Cryptography.SHA256]::Create()
    try{return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-','').ToLowerInvariant()}
    finally{$hash.Dispose();$stream.Dispose()}
}
function Resolve-SwirlMsvcPath([string]$Path) {
    if($Path -notmatch '^[A-Za-z]:[\\/]'){throw 'MSVC packaging requires an absolute local drive path.'}
    $full=[IO.Path]::GetFullPath($Path).TrimEnd('\','/')
    Assert-SwirlPathWithoutLinks $full
    return $full
}
function Get-SwirlMsvcPeGraph([string]$Root) {
    $rootPath=Resolve-SwirlMsvcPath $Root
    $images=@{};$rootImages=@{};$imports=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach($file in @(Get-ChildItem -LiteralPath $rootPath -Recurse -File -Force|Where-Object {$_.Extension -in @('.exe','.dll')})) {
        Assert-SwirlPathWithoutLinks $file.FullName
        $relative=$file.FullName.Substring($rootPath.Length+1).Replace('\','/')
        $pe=[SwirlMsvcPackage.PeImage]::Read($file.FullName)
        if($pe.Machine -cne '0x8664'){throw ('Non-AMD64 deployable PE image: '+$relative)}
        $key=$relative.ToLowerInvariant();if($images.ContainsKey($key)){throw 'Case-colliding PE names.'}
        $images[$key]=[ordered]@{path=$relative;machine=$pe.Machine;imports=@($pe.Imports);delay_imports=@($pe.DelayImports)}
        if($relative.IndexOf('/') -lt 0){$rootImages[$file.Name.ToLowerInvariant()]=$key}
        foreach($name in @($pe.Imports)+@($pe.DelayImports)) {
            $lower=$name.ToLowerInvariant()
            if($lower -match $script:SwirlMsvcNamePattern){$null=$imports.Add($lower)}
            elseif($lower -match '^(?:msvcr|msvcp|vcruntime|concrt|vccorlib|vcomp|mfc|mfcm|atl)[0-9].*\.dll$'){throw ('Unsupported compiler runtime dependency: '+$name)}
        }
    }
    if(-not $rootImages.ContainsKey('swirl.exe')){throw 'A real Swirl.exe is required for the runtime dependency graph.'}
    $loaded=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    $visited=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    $pending=New-Object 'System.Collections.Generic.Queue[string]';$pending.Enqueue('swirl.exe')
    while($pending.Count) {
        $key=$pending.Dequeue();if(-not $visited.Add($key)){continue}
        foreach($name in $images[$key].imports) {
            $lower=$name.ToLowerInvariant()
            if($lower -match $script:SwirlMsvcNamePattern){$null=$loaded.Add($lower)}
            if($rootImages.ContainsKey($lower)){$pending.Enqueue($rootImages[$lower])}
        }
    }
    foreach($core in $script:SwirlMsvcCoreModules){if(-not $loaded.Contains($core)){throw ('The application eager import graph does not contain expected core runtime: '+$core)}}
    return [ordered]@{images=$images;required_imports=@($imports|Sort-Object);required_modules=@($loaded|Sort-Object);optional_modules=@($imports|Where-Object {-not $loaded.Contains($_)}|Sort-Object)}
}
function Assert-SwirlMsvcRuntimePayload {
    param([Parameter(Mandatory=$true)][string]$ApplicationDirectory)
    $root=Resolve-SwirlMsvcPath $ApplicationDirectory
    $receiptPath=Join-Path $root 'msvc-runtime.json';Assert-SwirlPathWithoutLinks $receiptPath
    if(-not [IO.File]::Exists($receiptPath) -or (Get-Item -LiteralPath $receiptPath).Length -gt 65536){throw 'Missing or oversized app-local MSVC receipt.'}
    $receipt=Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8|ConvertFrom-Json
    if($receipt.schema -ne 1 -or $receipt.kind -cne 'msvc-app-local' -or $receipt.architecture -cne 'x64'){throw 'Invalid app-local MSVC receipt identity.'}
    $required=@($receipt.required_imports);$modules=@($receipt.required_modules);$optional=@($receipt.optional_modules)
    $fileNames=@($receipt.files.PSObject.Properties.Name)
    if(-not $required.Count -or @($required|Select-Object -Unique).Count -ne $required.Count -or @($required|Where-Object {$_ -cnotmatch $script:SwirlMsvcNamePattern}).Count -or @($modules|Select-Object -Unique).Count -ne $modules.Count -or @($optional|Select-Object -Unique).Count -ne $optional.Count -or @($modules|Where-Object {$_ -cnotin $required}).Count -or @($required|Where-Object {$_ -cnotin $fileNames}).Count -or @($fileNames|Where-Object {$_ -cnotin $required}).Count){throw 'Invalid app-local MSVC module set.'}
    foreach($name in $required) {
        $path=Join-Path $root $name;Assert-SwirlPathWithoutLinks $path
        if(-not [IO.File]::Exists($path)){throw ('Missing app-local compiler runtime: '+$name)}
        $entry=$receipt.files.PSObject.Properties[$name].Value
        if($entry.sha256 -cnotmatch '^[0-9a-f]{64}$' -or $entry.machine -cne '0x8664' -or (Get-Item -LiteralPath $path).Length -ne $entry.size -or (Get-SwirlMsvcHash $path) -cne $entry.sha256 -or [SwirlMsvcPackage.PeImage]::Read($path).Machine -cne '0x8664'){throw ('Invalid app-local compiler runtime bytes: '+$name)}
    }
    $graph=Get-SwirlMsvcPeGraph $root
    foreach($image in $graph.images.Values) {
        $basename=[IO.Path]::GetFileName([string]$image.path).ToLowerInvariant()
        if($basename -match $script:SwirlMsvcNamePattern -and ($image.path -cne $basename -or $basename -cnotin $required)){throw ('Unexpected compiler runtime image outside the receipt: '+$image.path)}
    }
    foreach($field in @('required_imports','required_modules','optional_modules')) {
        if((@($receipt.$field|Sort-Object) -join "`n") -cne (@($graph[$field]|Sort-Object) -join "`n")){throw ('MSVC receipt differs from actual PE imports: '+$field)}
    }
    return $receipt
}
function Copy-SwirlVerifiedMsvcRuntime {
    param([Parameter(Mandatory=$true)][string]$BuildDirectory,[Parameter(Mandatory=$true)][string]$ApplicationDirectory)
    $build=Resolve-SwirlMsvcPath ([IO.Path]::GetFullPath($BuildDirectory))
    $root=Resolve-SwirlMsvcPath ([IO.Path]::GetFullPath($ApplicationDirectory))
    if([IO.File]::Exists((Join-Path $root '.swirl-install-owned'))){throw 'Build-time CRT staging cannot modify an installed product.'}
    if([IO.File]::Exists((Join-Path $root 'vc_redist.x64.exe'))){throw 'Remove the known legacy bootstrap from this build stage before app-local deployment.'}
    $cache=Get-Content -LiteralPath (Join-Path $build 'CMakeCache.txt') -Raw -Encoding UTF8
    $parts=@();foreach($part in @('MAJOR','MINOR','PATCH')){if($cache -notmatch ('(?m)^CMAKE_CACHE_'+$part+'_VERSION:INTERNAL=([0-9]+)\s*$')){throw 'The active CMake version is missing.'};$parts+=$Matches[1]}
    $compilerFile=Join-Path $build ('CMakeFiles/'+($parts -join '.')+'/CMakeCXXCompiler.cmake')
    Assert-SwirlPathWithoutLinks $compilerFile
    $compilerText=Get-Content -LiteralPath $compilerFile -Raw -Encoding UTF8
    if($compilerText -notmatch '(?m)^set\(CMAKE_CXX_COMPILER_ID "MSVC"\)\s*$' -or $compilerText -notmatch '(?m)^set\(MSVC_CXX_ARCHITECTURE_ID "?x64"?\)\s*$'){throw 'Actual CMake compiler metadata must identify MSVC x64.'}
    if($compilerText -notmatch '(?m)^set\(CMAKE_CXX_COMPILER "([^"\r\n]+)"\)\s*$'){throw 'The actual CMake C++ compiler path is missing.'}
    $compiler=Resolve-SwirlMsvcPath $Matches[1]
    if(-not [IO.File]::Exists($compiler) -or $compiler -notmatch '^(?<vs>.+)[\\/]VC[\\/]Tools[\\/]MSVC[\\/](?<toolset>[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)[\\/]bin[\\/]Host(?:x64|x86)[\\/]x64[\\/]cl\.exe$'){throw 'Compiler path does not identify an installed MSVC x64 toolchain.'}
    $vs=Resolve-SwirlMsvcPath $Matches['vs'];$toolset=[version]$Matches['toolset']
    if($compilerText -notmatch '(?m)^set\(CMAKE_CXX_COMPILER_VERSION "([0-9.]+)"\)\s*$'){throw 'The actual C++ compiler version is missing.'}
    $compilerVersion=$Matches[1]
    $redistRoot=Join-Path $vs 'VC/Redist/MSVC';Assert-SwirlPathWithoutLinks $redistRoot
    $candidates=@(Get-ChildItem -LiteralPath $redistRoot -Directory|Where-Object {$_.Name -match '^[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?$' -and [version]$_.Name -ge $toolset}|Sort-Object @{Expression={[version]$_.Name};Descending=$true})
    $selected=$null;$crt=$null
    foreach($candidate in $candidates) {
        Assert-SwirlPathWithoutLinks $candidate.FullName
        $x64=Join-Path $candidate.FullName 'x64';if(-not [IO.Directory]::Exists($x64)){continue};Assert-SwirlPathWithoutLinks $x64
        $directories=@(Get-ChildItem -LiteralPath $x64 -Directory|Where-Object {$_.Name -match '^Microsoft\.VC[0-9]+\.CRT$'})
        if($directories.Count -gt 1){throw 'Ambiguous MSVC redistributable CRT directory.'}
        if($directories.Count -eq 1){$selected=$candidate;$crt=Resolve-SwirlMsvcPath $directories[0].FullName;break}
    }
    if($null -eq $selected){throw 'No same-toolchain x64 redistributable CRT at least as recent as the compiler toolset is installed.'}
    $graph=Get-SwirlMsvcPeGraph $root
    $needed=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    $queue=New-Object 'System.Collections.Generic.Queue[string]'
    foreach($name in $graph.required_imports){$null=$needed.Add($name);$queue.Enqueue($name)}
    $files=[ordered]@{}
    while($queue.Count) {
        $name=$queue.Dequeue();$source=Join-Path $crt $name;Assert-SwirlPathWithoutLinks $source
        if(-not [IO.File]::Exists($source)){throw ('Required CRT is missing from the selected official redist directory: '+$name)}
        $image=[SwirlMsvcPackage.PeImage]::Read($source)
        if($image.Machine -cne '0x8664'){throw ('Wrong architecture in the x64 CRT source: '+$name)}
        $info=[Diagnostics.FileVersionInfo]::GetVersionInfo($source)
        $version=[version]('{0}.{1}.{2}.{3}' -f $info.FileMajorPart,$info.FileMinorPart,$info.FileBuildPart,$info.FilePrivatePart)
        if($version -lt $toolset){throw ('Redistributable DLL predates the actual compiler toolset: '+$name)}
        $signature=Get-AuthenticodeSignature -LiteralPath $source
        if($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate -or $signature.SignerCertificate.Subject -notmatch '(?:^|,\s*)O=Microsoft Corporation(?:,|$)'){throw ('CRT source does not have a valid Microsoft signature: '+$name)}
        $hash=Get-SwirlMsvcHash $source;$destination=Join-Path $root $name;Assert-SwirlPathWithoutLinks $destination
        [IO.File]::Copy($source,$destination,$true)
        if((Get-SwirlMsvcHash $destination) -cne $hash -or (Get-SwirlMsvcHash $source) -cne $hash){throw ('CRT source or destination changed during copy: '+$name)}
        $files[$name]=[ordered]@{sha256=$hash;size=(Get-Item -LiteralPath $destination).Length;machine=$image.Machine;file_version=$version.ToString();source_relative=$source.Substring($vs.Length+1).Replace('\','/');signature_status=$signature.Status.ToString();signer_subject=$signature.SignerCertificate.Subject;signer_thumbprint=$signature.SignerCertificate.Thumbprint}
        foreach($dependency in @($image.Imports)+@($image.DelayImports)) {
            $lower=$dependency.ToLowerInvariant();if($lower -match $script:SwirlMsvcNamePattern -and $needed.Add($lower)){$queue.Enqueue($lower)}
        }
    }
    $graph=Get-SwirlMsvcPeGraph $root
    $receipt=[ordered]@{schema=1;kind='msvc-app-local';architecture='x64';source=[ordered]@{compiler_path=$compiler;compiler_sha256=(Get-SwirlMsvcHash $compiler);compiler_version=$compilerVersion;toolset_version=$toolset.ToString();visual_studio_root=$vs;crt_directory=$crt;redist_version=$selected.Name};required_imports=$graph.required_imports;required_modules=$graph.required_modules;optional_modules=$graph.optional_modules;files=$files}
    $json=ConvertTo-Json -InputObject $receipt -Depth 10
    if([Text.Encoding]::UTF8.GetByteCount($json) -gt 65536){throw 'MSVC runtime receipt exceeds the native 64 KiB bound.'}
    [IO.File]::WriteAllText((Join-Path $root 'msvc-runtime.json'),$json,(New-Object Text.UTF8Encoding $false))
    $null=Assert-SwirlMsvcRuntimePayload -ApplicationDirectory $root
    return $receipt
}
if($BuildDirectory -or $ApplicationDirectory) {
    if(-not $BuildDirectory -or -not $ApplicationDirectory){throw 'Specify both BuildDirectory and ApplicationDirectory.'}
    $result=Copy-SwirlVerifiedMsvcRuntime -BuildDirectory $BuildDirectory -ApplicationDirectory $ApplicationDirectory
    Write-Host ('Verified application-local Microsoft CRT: '+($result.required_imports -join ', '))
}
