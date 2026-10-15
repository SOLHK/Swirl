param(
    [Parameter(Mandatory)][string]$QtDir,
    [string]$BuildDir='build/interaction',
    [string]$EvidenceDir='out/interaction',
    [switch]$Live,
    [switch]$Profile
)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
if(-not [IO.Path]::IsPathRooted($BuildDir)){$BuildDir=Join-Path $repo $BuildDir}
if(-not [IO.Path]::IsPathRooted($EvidenceDir)){$EvidenceDir=Join-Path $repo $EvidenceDir}
$saved=@{}
foreach($name in @('PATH','QT_QPA_PLATFORM','QT_QUICK_BACKEND','QSG_RHI_BACKEND','SWIRL_SCROLL_BENCH','SWIRL_SCROLL_LIVE','SWIRL_QML_PROFILE')){$saved[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
try {
    $env:PATH="$(Join-Path $QtDir 'bin');$env:PATH"
    $env:QT_QPA_PLATFORM='windows';$env:QT_QUICK_BACKEND=$null;$env:QSG_RHI_BACKEND='d3d11'
    cmake -S (Join-Path $repo 'src/Swirl.Quick') -B $BuildDir -G Ninja -DCMAKE_BUILD_TYPE=Release "-DCMAKE_PREFIX_PATH=$QtDir" -DSWIRL_BUILD_UI_TESTS=ON
    if($LASTEXITCODE){throw 'Configure failed'}
    cmake --build $BuildDir --parallel 6
    if($LASTEXITCODE){throw 'Build failed'}
    New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
    $app=Join-Path $BuildDir 'Swirl.exe'
    $env:SWIRL_SCROLL_BENCH='1';$env:SWIRL_SCROLL_LIVE=if($Live){'1'}else{$null}
    $report=Join-Path $EvidenceDir 'scroll.json'
    $run=Start-Process -FilePath $app -ArgumentList @('--motion-test',('"--motion-output='+$report+'"')) -Wait -PassThru -WindowStyle Hidden
    if($run.ExitCode){throw "Scroll acceptance failed: $($run.ExitCode)"}
    if($Profile){
        # Separate profiled run: tracing overhead must not enter scroll.json.
        $env:SWIRL_QML_PROFILE='1'
        & (Join-Path $QtDir 'bin/qmlprofiler.exe') --port 43768 --output (Join-Path $EvidenceDir 'qml-trace.qtd') --include javascript,binding,handlingsignal,scenegraph,painting,animations $app --motion-test "--motion-output=$(Join-Path $EvidenceDir 'profiled-scroll.json')"
        if($LASTEXITCODE){throw 'QML trace collection failed'}
    }
    Write-Output "Evidence: $EvidenceDir"
} finally {
    foreach($name in $saved.Keys){[Environment]::SetEnvironmentVariable($name,$saved[$name],'Process')}
}
