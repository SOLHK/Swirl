# Test-only real shortcut creation shared by the early x86 standard-user gate
# and the ordinary installer lifecycle. WScript.Shell fails to save some
# Unicode filenames on the actual Windows PowerShell 5.1 runner. Keep the full
# requested filename and use Unicode .NET file I/O around ASCII COM staging.
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
    $shell=$null;$link=$null;$verify=$null;$failure=$null
    $expectedUnits=[ordered]@{target=@($target.ToCharArray()|ForEach-Object {[int]$_});arguments=@('-NoProfile'.ToCharArray()|ForEach-Object {[int]$_});description=@($Description.ToCharArray()|ForEach-Object {[int]$_})}
    $result=[ordered]@{path=$destination;target=$target;arguments='-NoProfile';description=$Description;expected_utf16_code_units=$expectedUnits;observed_target=$null;observed_arguments=$null;observed_description=$null;observed_utf16_code_units=$null;target_matches=$false;arguments_match=$false;description_matches=$false;final_bytes_match=$false;stage_sha256=$null;stage_length=0;sha256=$null;length=0;bytes_base64=$null;staging_removed=$false;success=$false;error=$null}
    try {
        $shell=New-Object -ComObject WScript.Shell
        $link=$shell.CreateShortcut($staged)
        $link.TargetPath=$target;$link.Arguments='-NoProfile';$link.Description=$Description;$link.Save()
        $null=[Runtime.InteropServices.Marshal]::FinalReleaseComObject($link);$link=$null
        [byte[]]$expected=[IO.File]::ReadAllBytes($staged)
        $result.stage_sha256=Get-SwirlIntegrationHash $staged;$result.stage_length=$expected.Length
        if($expected.Length -eq 0 -or $expected.Length -gt 262144){throw 'The real shortcut fixture has an invalid size.'}
        Write-SwirlIntegrationFile $destination $expected
        # Read the actual final Unicode filename, not the original staged file.
        # Inspect a new ASCII copy of these bytes to avoid the same COM filename
        # conversion during load; semantic metadata still comes from that file.
        [byte[]]$actual=[IO.File]::ReadAllBytes($destination)
        $result.sha256=Get-SwirlIntegrationHash $destination
        $result.length=$actual.Length;$result.bytes_base64=[Convert]::ToBase64String($actual)
        $result.final_bytes_match=[Convert]::ToBase64String($actual) -ceq [Convert]::ToBase64String($expected)
        if(-not $result.final_bytes_match){throw 'The final Unicode shortcut bytes differ from the staged shortcut.'}
        [IO.File]::WriteAllBytes($readback,$actual)
        $verify=$shell.CreateShortcut($readback)
        $result.observed_target=[string]$verify.TargetPath
        $result.observed_arguments=[string]$verify.Arguments
        $result.observed_description=[string]$verify.Description
        $result.observed_utf16_code_units=[ordered]@{target=@($result.observed_target.ToCharArray()|ForEach-Object {[int]$_});arguments=@($result.observed_arguments.ToCharArray()|ForEach-Object {[int]$_});description=@($result.observed_description.ToCharArray()|ForEach-Object {[int]$_})}
        $result.target_matches=[IO.Path]::GetFullPath($result.observed_target) -ieq [IO.Path]::GetFullPath($target)
        $result.arguments_match=$result.observed_arguments -ceq $result.arguments
        $result.description_matches=$result.observed_description -ceq $Description
        if(-not $result.target_matches -or -not $result.arguments_match -or -not $result.description_matches){throw 'The final Unicode shortcut target, arguments or exact description did not round-trip.'}
        $result.success=$true
    }catch{$failure=$_.Exception.Message}
    finally {
        try {
            if($null -ne $verify){$null=[Runtime.InteropServices.Marshal]::FinalReleaseComObject($verify)}
            if($null -ne $link){$null=[Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}
            if($null -ne $shell){$null=[Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
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
