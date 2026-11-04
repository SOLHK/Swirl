; Per-user companion monitor. It does not replace Swirl or alter network settings.
!include "MUI2.nsh"
!include "FileFunc.nsh"
Unicode true
SetCompressor /SOLID zlib

!ifndef REPO_DIR
!error "REPO_DIR is required"
!endif
!ifndef OUT_DIR
!error "OUT_DIR is required"
!endif
!ifndef SOURCE_SHORT
!error "SOURCE_SHORT is required"
!endif

Var IsolatedInstall
Var Parameters
Name "Swirl Core 全天候验收"
OutFile "${OUT_DIR}\Swirl-Core-Monitor-Setup-${SOURCE_SHORT}.exe"
InstallDir "D:\Codex\SwirlCoreMonitor"
RequestExecutionLevel user
ShowInstDetails show
ShowUnInstDetails show
VIProductVersion "0.1.0.0"
VIAddVersionKey /LANG=2052 "ProductName" "Swirl Core 全天候验收"
VIAddVersionKey /LANG=2052 "FileDescription" "Swirl Core 全天候验收安装程序"
VIAddVersionKey /LANG=2052 "ProductVersion" "0.1.0.0"
VIAddVersionKey /LANG=2052 "FileVersion" "0.1.0.0"
VIAddVersionKey /LANG=2052 "LegalCopyright" "Copyright SOLHK"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Function .onInit
    IfFileExists "$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" native_ok
    Abort "需要 64 位 Windows PowerShell。"
    native_ok:
    StrCpy $IsolatedInstall "0"
    ${GetParameters} $Parameters
    ClearErrors
    ${GetOptions} $Parameters "/ISOLATED" $0
    IfErrors init_done
    StrCpy $IsolatedInstall "1"
    init_done:
FunctionEnd

Section "安装全天候验收工具"
    SetShellVarContext current
    StrCmp $INSTDIR "D:\Codex\SwirlCoreMonitor" path_ok
    Abort "本工具只安装到 D:\Codex\SwirlCoreMonitor。"
    path_ok:
    IfFileExists "$INSTDIR\*.*" existing copy_files
    existing:
    IfFileExists "$INSTDIR\.swirl-monitor-owned" owned
    Abort "安装目录已有非本工具文件，停止安装。"
    owned:
    StrCmp $IsolatedInstall "1" copy_files
    nsExec::ExecToStack '"$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\Stop-SwirlCoreMonitor.ps1"'
    Pop $0
    Pop $1
    StrCmp $0 "0" copy_files
    Abort "旧监控进程未停止；未覆盖安装文件。"
    copy_files:
    SetOutPath "$INSTDIR"
    SetOverwrite on
    File "${REPO_DIR}\tools\Test-SwirlCoreOffline.ps1"
    File "${REPO_DIR}\tools\Test-SwirlMihomoPath.ps1"
    File "${REPO_DIR}\tools\Test-SwirlPrivateDirect.ps1"
    File "${REPO_DIR}\tools\Monitor-SwirlCore.ps1"
    File "${REPO_DIR}\tools\Start-SwirlCoreMonitor.ps1"
    File "${REPO_DIR}\tools\Stop-SwirlCoreMonitor.ps1"
    File "${REPO_DIR}\tools\SwirlCoreMonitor.config.json"
    File "${REPO_DIR}\tools\Run-SwirlCoreMonitor.cmd"
    File "${REPO_DIR}\tools\Stop-SwirlCoreMonitor.cmd"
    File "${REPO_DIR}\tools\Open-SwirlCoreMonitorReport.cmd"
    File /oname=README-先看.txt "${REPO_DIR}\src\Swirl.Quick\packaging\README-SwirlCoreMonitor.txt"
    FileOpen $0 "$INSTDIR\.swirl-monitor-owned" w
    FileWrite $0 "Swirl Core Monitor"
    FileClose $0
    WriteUninstaller "$INSTDIR\Uninstall-SwirlCoreMonitor.exe"
    StrCmp $IsolatedInstall "1" isolated regular
    isolated:
    FileOpen $0 "$INSTDIR\.swirl-monitor-isolated" w
    FileClose $0
    Goto done
    regular:
    Delete "$INSTDIR\.swirl-monitor-isolated"
    CreateDirectory "$SMPROGRAMS\Swirl Core 全天候验收"
    CreateShortCut "$SMPROGRAMS\Swirl Core 全天候验收\启动监控.lnk" "$INSTDIR\Run-SwirlCoreMonitor.cmd"
    CreateShortCut "$SMPROGRAMS\Swirl Core 全天候验收\停止监控.lnk" "$INSTDIR\Stop-SwirlCoreMonitor.cmd"
    CreateShortCut "$SMPROGRAMS\Swirl Core 全天候验收\查看报告.lnk" "$INSTDIR\Open-SwirlCoreMonitorReport.cmd"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlCoreMonitor" "DisplayName" "Swirl Core 全天候验收"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlCoreMonitor" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlCoreMonitor" "UninstallString" '"$INSTDIR\Uninstall-SwirlCoreMonitor.exe"'
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlCoreMonitor" "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlCoreMonitor" "NoRepair" 1
    nsExec::ExecToStack '"$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\Start-SwirlCoreMonitor.ps1"'
    Pop $0
    Pop $1
    StrCmp $0 "0" done
    DetailPrint "后台启动未成功；可从开始菜单手动启动。"
    done:
SectionEnd

Function un.onInit
    IfFileExists "$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" native_ok
    Abort "需要 64 位 Windows PowerShell 才能安全停止监控。"
    native_ok:
    StrCmp $INSTDIR "D:\Codex\SwirlCoreMonitor" path_ok
    Abort "卸载路径不是本工具的固定目录。"
    path_ok:
    IfFileExists "$INSTDIR\.swirl-monitor-owned" owned
    Abort "缺少安装目录标记，停止卸载。"
    owned:
FunctionEnd

Section "Uninstall"
    SetShellVarContext current
    IfFileExists "$INSTDIR\.swirl-monitor-isolated" isolated regular
    regular:
    nsExec::ExecToStack '"$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\Stop-SwirlCoreMonitor.ps1"'
    Pop $0
    Pop $1
    StrCmp $0 "0" stopped
    Abort "监控进程未停止，保留安装文件。"
    stopped:
    Delete "$SMPROGRAMS\Swirl Core 全天候验收\启动监控.lnk"
    Delete "$SMPROGRAMS\Swirl Core 全天候验收\停止监控.lnk"
    Delete "$SMPROGRAMS\Swirl Core 全天候验收\查看报告.lnk"
    RMDir "$SMPROGRAMS\Swirl Core 全天候验收"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlCoreMonitor"
    isolated:
    Delete "$INSTDIR\Test-SwirlCoreOffline.ps1"
    Delete "$INSTDIR\Test-SwirlMihomoPath.ps1"
    Delete "$INSTDIR\Test-SwirlPrivateDirect.ps1"
    Delete "$INSTDIR\Monitor-SwirlCore.ps1"
    Delete "$INSTDIR\Start-SwirlCoreMonitor.ps1"
    Delete "$INSTDIR\Stop-SwirlCoreMonitor.ps1"
    Delete "$INSTDIR\SwirlCoreMonitor.config.json"
    Delete "$INSTDIR\Run-SwirlCoreMonitor.cmd"
    Delete "$INSTDIR\Stop-SwirlCoreMonitor.cmd"
    Delete "$INSTDIR\Open-SwirlCoreMonitorReport.cmd"
    Delete "$INSTDIR\README-先看.txt"
    Delete "$INSTDIR\Uninstall-SwirlCoreMonitor.exe"
    Delete "$INSTDIR\.swirl-monitor-isolated"
    Delete "$INSTDIR\.swirl-monitor-owned"
    RMDir "$INSTDIR"
    ; Monitoring history and user config under D:\Codex\SwirlCoreMonitorData are retained.
SectionEnd
