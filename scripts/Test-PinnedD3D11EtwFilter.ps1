#Requires -Version 7.4
param(
    [Parameter(Mandatory)][string]$XmlPath,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [Parameter(Mandatory)][int[]]$ProcessIds
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$state=[ordered]@{complete=$false;first_pass_complete=$false;events_scanned=0;retained_events=0;target_threads=@();command_line_fields=0;opaque_events=0;elapsed_ms=0;errors=@();jsonl_bytes=0}
$targets=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
$threads=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($id in $ProcessIds) { if ($id -gt 0) { $null=$targets.Add([string]$id) } }
$clock=[Diagnostics.Stopwatch]::StartNew(); $writer=$null; $phase='admission'
$errors=[Collections.Generic.List[string]]::new()
function Etw-NumericId([string]$Value) {
    [uint64]$number=0
    if ($Value -match '^0x([0-9a-fA-F]+)$') { return [Convert]::ToUInt64($Matches[1],16).ToString() }
    if ([uint64]::TryParse($Value,[ref]$number)) { return $number.ToString() }
    return ''
}
function Read-EtwRecord([Xml.XmlDocument]$Document,[long]$Ordinal) {
    $system=$Document.SelectSingleNode('/*[local-name()="Event"]/*[local-name()="System"]')
    if (-not $system) { return $null }
    $provider=$system.SelectSingleNode('*[local-name()="Provider"]')
    $execution=$system.SelectSingleNode('*[local-name()="Execution"]')
    $time=$system.SelectSingleNode('*[local-name()="TimeCreated"]')
    $row=[ordered]@{ordinal=$Ordinal;provider='';provider_guid='';pid='';tid='';event_id='';task='';opcode='';time=[ordered]@{};data=@()}
    if ($provider) { $row.provider=$provider.GetAttribute('Name'); $row.provider_guid=$provider.GetAttribute('Guid') }
    if ($execution) { $row.pid=Etw-NumericId $execution.GetAttribute('ProcessID'); $row.tid=Etw-NumericId $execution.GetAttribute('ThreadID') }
    foreach ($pair in @(@('EventID','event_id'),@('Task','task'),@('Opcode','opcode'))) {
        $node=$system.SelectSingleNode('*[local-name()="' + $pair[0] + '"]')
        if ($node) { $row[$pair[1]]=$node.InnerText }
    }
    if ($time) { foreach ($attribute in $time.Attributes) { $row.time[$attribute.LocalName]=$attribute.Value } }
    $data=[Collections.Generic.List[object]]::new()
    foreach ($node in $Document.SelectNodes('/*[local-name()="Event"]/*[local-name()="EventData" or local-name()="UserData"]//*[not(*)]')) {
        $name=$node.GetAttribute('Name'); if (-not $name) { $name=$node.LocalName }
        $data.Add([ordered]@{name=$name;value=$node.InnerText})
    }
    $row.data=$data.ToArray(); return $row
}
function Visit-EtwXml([scriptblock]$Action) {
    $settings=[Xml.XmlReaderSettings]::new(); $settings.DtdProcessing=[Xml.DtdProcessing]::Prohibit
    $settings.XmlResolver=$null; $settings.IgnoreWhitespace=$true
    $reader=[Xml.XmlReader]::Create($XmlPath,$settings); [long]$ordinal=0
    try {
        while ($reader.Read()) {
            if ($reader.NodeType -ne [Xml.XmlNodeType]::Element -or $reader.LocalName -cne 'Event') { continue }
            ++$ordinal
            if ($clock.ElapsedMilliseconds -ge 60000) { throw 'Trace filtering deadline reached.' }
            $sub=$reader.ReadSubtree()
            try { $document=[Xml.XmlDocument]::new(); $document.XmlResolver=$null; $document.Load($sub) } finally { $sub.Dispose() }
            & $Action $document $ordinal
        }
    } finally { $reader.Dispose() }
}
try {
    if ($targets.Count -eq 0 -or -not (Test-Path -LiteralPath $XmlPath -PathType Leaf) -or (Get-Item -LiteralPath $XmlPath).Length -gt 536870912) { throw 'Invalid bounded trace input.' }
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $destination=Join-Path $OutputDirectory 'target-events.jsonl'
    if (Test-Path -LiteralPath $destination) { throw 'Filtered event evidence already exists.' }
    $phase='scan'
    Visit-EtwXml {
        param($document,$ordinal)
        $state.events_scanned=$ordinal
        $opaque=$false
        foreach ($node in $document.SelectNodes('//* | //@*')) {
            $name=$node.LocalName
            if ($node -is [Xml.XmlElement] -and $node.HasAttribute('Name')) { $name += ' ' + $node.GetAttribute('Name') }
            $value=if ($node -is [Xml.XmlAttribute]) { $node.Value } else { $node.InnerText }
            if ($name -match '(?i)command.?line|cmd.?line' -and -not [string]::IsNullOrWhiteSpace($value)) { $state.command_line_fields++ }
            if ($node.LocalName -ceq 'Binary' -and -not [string]::IsNullOrWhiteSpace($value)) { $opaque=$true }
        }
        if ($opaque) { $state.opaque_events++ }
        $row=Read-EtwRecord $document $ordinal
        if (-not $row) { $state.opaque_events++ }
        if ($row -and $targets.Contains($row.pid) -and $row.provider -ceq 'Microsoft-Windows-DXGI' -and $row.tid) { $null=$threads.Add($row.tid) }
    }
    $state.first_pass_complete=$true; $state.target_threads=@($threads | Sort-Object)
    if ($threads.Count -eq 0) { throw 'No target DXGI thread could be identified from decoded event headers.' }
    $phase='filter'; $writer=[IO.StreamWriter]::new($destination,$false,[Text.UTF8Encoding]::new($false)); $writer.NewLine="`n"
    Visit-EtwXml {
        param($document,$ordinal)
        # An undecoded target payload must not become public merely by moving
        # from the withheld ETL into JSONL. Retain no payload from that event.
        foreach ($node in $document.SelectNodes('//*[local-name()="Binary"]')) {
            if (-not [string]::IsNullOrWhiteSpace($node.InnerText)) { return }
        }
        $row=Read-EtwRecord $document $ordinal
        if (-not $row) { return }
        $keep=$targets.Contains($row.pid) -or $threads.Contains($row.tid)
        foreach ($item in $row.data) {
            if ($item.name -match '(?i)command.?line|cmd.?line') { return }
            $value=Etw-NumericId $item.value
            if ($item.name -match '(?i)^(process_?id|pid|StackProcess)$' -and $targets.Contains($value)) { $keep=$true }
            # ReadyThread names its target TThreadId; StackWalk uses StackThread.
            # Keep EventTimeStamp in row.data to join each stack to its event.
            if ($item.name -match '(?i)^((old|new)?thread_?id|tid|TThreadId|StackThread)$' -and $threads.Contains($value)) { $keep=$true }
        }
        if (-not $keep) { return }
        $line=ConvertTo-Json -InputObject $row -Depth 8 -Compress
        $length=[Text.Encoding]::UTF8.GetByteCount($line)+1
        if ($state.jsonl_bytes+$length -gt 67108864) { throw 'Filtered event size bound reached.' }
        $writer.WriteLine($line); $state.jsonl_bytes+=$length; $state.retained_events++
    }
    $state.complete=($state.retained_events -gt 0)
} catch { $errors.Add($phase + ':' + $_.Exception.GetType().Name) }
finally {
    if ($writer) { $writer.Dispose() }; $clock.Stop(); $state.elapsed_ms=$clock.Elapsed.TotalMilliseconds
    $state.errors=$errors.ToArray()
}
return $state
