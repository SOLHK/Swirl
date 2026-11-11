!include "MUI2.nsh"
!include "FileFunc.nsh"
Unicode true
SetCompressor /SOLID lzma
Var IsolatedInstall
Var Parameters
Var FailurePhase
Var FailureCode
!ifndef APP_DIST
!error "APP_DIST is required"
!endif
!ifndef OUT_DIR
!error "OUT_DIR is required"
!endif
!ifndef APP_ICON
!error "APP_ICON required (generated from Swirl SVG)"
!endif
!ifndef APP_VERSION
!error "APP_VERSION is required (read PRODUCT_VERSION.txt)"
!endif
!ifndef UNINSTALL_LIST
!error "UNINSTALL_LIST is required (generated from the verified package manifest)"
!endif
!ifndef REPO_ROOT
!error "REPO_ROOT is required (absolute repository path supplied by the build caller)"
!endif
!include "${UNINSTALL_LIST}"
!ifndef SWIRL_VERIFIED_SOURCE_SHA
!error "The final package verification include is invalid"
!endif
!define MUI_ABORTWARNING
!define MUI_ICON "${APP_ICON}"
!define MUI_UNICON "${APP_ICON}"
!define MUI_FINISHPAGE_RUN "$INSTDIR\\Swirl.exe"
!define MUI_FINISHPAGE_RUN_TEXT "启动 Swirl"
Name "Swirl"
OutFile "${OUT_DIR}\\Swirl-Setup.exe"
InstallDir "$LOCALAPPDATA\\Programs\\Swirl"
InstallDirRegKey HKCU "Software\\Swirl" "InstallDir"
RequestExecutionLevel user
ShowInstDetails show
ShowUnInstDetails show
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey /LANG=2052 "ProductName" "Swirl"
VIAddVersionKey /LANG=2052 "FileDescription" "Swirl 安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "${APP_VERSION}.0"
VIAddVersionKey /LANG=2052 "ProductVersion" "${APP_VERSION}.0"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"
!macro ValidateIsolatedDirectory
    ; Resolve traversal and reject junction ancestors before touching a fixture.
    ; NSIS GetFullPathName can return empty for a fresh nonexistent directory.
    System::Call 'kernel32::GetFullPathNameW(w "$INSTDIR", i ${NSIS_MAX_STRLEN}, w .r0, p 0) i.r2'
    IntCmp $2 0 isolated_path_invalid isolated_path_invalid +1
    IntCmp $2 ${NSIS_MAX_STRLEN} isolated_path_invalid +1 isolated_path_invalid
    ReadEnvStr $3 "SWIRL_ISOLATED_INSTALL_ROOT"
    StrCmp $3 "" isolated_path_invalid
    StrCpy $3 "$3\install"
    StrCmp $0 $3 0 isolated_path_invalid
    StrCpy $INSTDIR $0
    StrCpy $1 $0 16
    StrCmp $1 "D:\Codex\tmp\s4\" 0 isolated_path_invalid
    StrLen $1 $0
    IntCmp $1 16 isolated_path_invalid isolated_path_invalid isolated_check_links
    isolated_check_links:
    System::Call 'kernel32::GetFileAttributesW(w r0) i.r2'
    StrCmp $2 "-1" isolated_parent
    IntOp $2 $2 & 0x400
    IntCmp $2 0 isolated_parent isolated_path_invalid isolated_path_invalid
    isolated_parent:
    ${GetParent} "$0" $0
    StrLen $1 $0
    IntCmp $1 3 isolated_path_valid isolated_path_valid isolated_check_links
    isolated_path_invalid:
    SetErrorLevel 2
    Abort "隔离验证仅允许 D:\Codex\tmp\s4 下不含目录链接的专用测试目录。"
    isolated_path_valid:
!macroend
!macro PreparePackageMaintenance
    InitPluginsDir
    SetOutPath "$PLUGINSDIR"
    File /oname=Maintain-WindowsRustProduct.ps1 "${REPO_ROOT}\scripts\Maintain-WindowsRustProduct.ps1"
    File /oname=RustProductPackagePolicy.ps1 "${REPO_ROOT}\scripts\RustProductPackagePolicy.ps1"
    File /oname=WindowsUserIntegration.ps1 "${REPO_ROOT}\scripts\WindowsUserIntegration.ps1"
    File /oname=package-manifest.json "${APP_DIST}\package-manifest.json"
!macroend
!macro MaintainPackage Mode ExtraArguments FailureLabel
    StrCpy $FailurePhase "package-${Mode}"
    nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "$PLUGINSDIR\Maintain-WindowsRustProduct.ps1" -Mode ${Mode} -ApplicationDirectory "$INSTDIR" -ExpectedManifest "$PLUGINSDIR\package-manifest.json" ${ExtraArguments}'
    Pop $0
    Pop $1
    StrCpy $FailureCode $0
    DetailPrint "$1"
    !ifdef PACKAGE_TEST_TRACE
    FileOpen $9 "${PACKAGE_TEST_TRACE}" a
    FileSeek $9 0 END
    FileWrite $9 "${Mode}: exit=$0 output=$1$\r$\n"
    FileClose $9
    !endif
    StrCmp $0 "0" +2
    Goto ${FailureLabel}
!macroend
!macro MaintainUserIntegration Mode FailureLabel
    StrCpy $FailurePhase "user-integration-${Mode}"
    nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "$PLUGINSDIR\WindowsUserIntegration.ps1" -Mode ${Mode} -ApplicationDirectory "$INSTDIR" -ExpectedManifest "$PLUGINSDIR\package-manifest.json" -AppVersion "${APP_VERSION}"'
    Pop $0
    Pop $1
    StrCpy $FailureCode $0
    DetailPrint "$1"
    StrCmp $0 "0" +2
    Goto ${FailureLabel}
!macroend
!macro RequireNativeTunRecovery FailureLabel
    ; The path-validated isolated installer never owns the host's TUN session.
    StrCmp $IsolatedInstall "1" native_tun_checked
    ; Query the exact REG_DWORD in the same explicit 32-bit view as the GUI.
    ; A missing marker does not launch anything or request elevation.
    StrCpy $FailurePhase "native-tun-marker-open"
    System::Call 'advapi32::RegOpenKeyExW(p 0x80000001, w "Software\SOLHK\Swirl\NativeTun", i 0, i 0x201, *p.r1) i.r0'
    StrCpy $FailureCode $0
    StrCmp $0 "2" native_tun_checked
    StrCmp $0 "0" 0 ${FailureLabel}
    StrCpy $5 "4"
    StrCpy $FailurePhase "native-tun-marker-query"
    System::Call 'advapi32::RegQueryValueExW(p r1, w "recoveryPending", p 0, *i.r2, *i.r3, *i r5r5) i.r0'
    StrCpy $FailureCode $0
    System::Call 'advapi32::RegCloseKey(p r1)'
    StrCmp $0 "2" native_tun_checked
    StrCmp $0 "0" 0 ${FailureLabel}
    StrCpy $FailurePhase "native-tun-marker-type"
    StrCpy $FailureCode $2
    StrCmp $2 "4" 0 ${FailureLabel}
    StrCpy $FailurePhase "native-tun-marker-size"
    StrCpy $FailureCode $5
    StrCmp $5 "4" 0 ${FailureLabel}
    StrCmp $3 "0" native_tun_checked
    StrCpy $FailurePhase "native-tun-marker-value"
    StrCpy $FailureCode $3
    StrCmp $3 "1" 0 ${FailureLabel}
    ; A genuinely fresh destination has no old recovery payload to overwrite.
    IfFileExists "$INSTDIR\Swirl.exe" native_tun_owned
    StrCpy $FailurePhase "native-tun-payload"
    StrCpy $FailureCode "missing-payload"
    IfFileExists "$INSTDIR\swirl-tun-broker.exe" ${FailureLabel}
    IfFileExists "$INSTDIR\swirl-tun-helper.exe" ${FailureLabel}
    IfFileExists "$INSTDIR\package-manifest.json" ${FailureLabel}
    IfFileExists "$INSTDIR\.swirl-install-owned" ${FailureLabel}
    Goto native_tun_checked
    native_tun_owned:
    StrCpy $FailurePhase "native-tun-payload"
    StrCpy $FailureCode "missing-payload"
    IfFileExists "$INSTDIR\.swirl-install-owned" 0 ${FailureLabel}
    IfFileExists "$INSTDIR\package-manifest.json" 0 ${FailureLabel}
    IfFileExists "$INSTDIR\swirl-tun-broker.exe" 0 ${FailureLabel}
    IfFileExists "$INSTDIR\swirl-tun-helper.exe" 0 ${FailureLabel}
    IfFileExists "$INSTDIR\wintun.dll" 0 ${FailureLabel}
    IfFileExists "$INSTDIR\tun-runtime.json" 0 ${FailureLabel}
    ; Verify the currently installed owner and bytes before executing its
    ; maintenance entry. The new package's manifest describes another version.
    StrCpy $FailurePhase "native-tun-installed-verify"
    nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "$PLUGINSDIR\Maintain-WindowsRustProduct.ps1" -Mode Verify -ApplicationDirectory "$INSTDIR" -ExpectedManifest "$INSTDIR\package-manifest.json"'
    Pop $0
    Pop $1
    StrCpy $FailureCode $0
    DetailPrint "$1"
    StrCmp $0 "0" 0 ${FailureLabel}
    ; Restoring host network state requires the user's explicit action.
    ; A silent upgrade cannot consent on the user's behalf.
    StrCpy $FailurePhase "native-tun-consent"
    StrCpy $FailureCode "required"
    IfSilent ${FailureLabel}
    MessageBox MB_OKCANCEL|MB_ICONINFORMATION "上次 Swirl TUN 网络恢复尚未确认。继续前需要管理员授权，恢复 Swirl 自己接管的网络设置；发生冲突时会保留恢复记录并停止更新。是否现在恢复？" IDOK +2 IDCANCEL ${FailureLabel}
    Goto ${FailureLabel}
    ClearErrors
    StrCpy $FailurePhase "native-tun-maintenance"
    StrCpy $FailureCode "unavailable"
    ExecWait '"$INSTDIR\Swirl.exe" --recover-tun' $0
    IfErrors ${FailureLabel}
    StrCpy $FailureCode $0
    StrCmp $0 "0" 0 ${FailureLabel}
    SetRegView 32
    ClearErrors
    StrCpy $FailurePhase "native-tun-marker-confirm"
    StrCpy $FailureCode "unavailable"
    ReadRegDWORD $0 HKCU "Software\SOLHK\Swirl\NativeTun" "recoveryPending"
    IfErrors ${FailureLabel}
    StrCpy $FailureCode $0
    StrCmp $0 "0" 0 ${FailureLabel}
    native_tun_checked:
!macroend
!macro EmitFailureReceipt Kind
    ; One bounded ASCII receipt reaches an existing inherited stderr handle.
    ; Ordinary GUI launches have no such handle and create no diagnostic file.
    System::Call 'kernel32::GetStdHandle(i -12) p.r0'
    StrCmp $0 "0" ${Kind}_receipt_done
    StrCmp $0 "-1" ${Kind}_receipt_done
    StrCpy $1 "SWIRL_${Kind}_FAILURE phase=$FailurePhase code=$FailureCode$\r$\n"
    StrLen $2 $1
    System::Call 'kernel32::WriteFile(p r0, m r1, i r2, *i.r3, p 0) i'
    ${Kind}_receipt_done:
!macroend
Function .onInit
    StrCpy $IsolatedInstall "0"
    ${GetParameters} $Parameters
    ClearErrors
    ${GetOptions} $Parameters "/ISOLATED" $0
    IfErrors +2 0
    StrCpy $IsolatedInstall "1"
    StrCmp $IsolatedInstall "1" 0 init_done
    !insertmacro ValidateIsolatedDirectory
    init_done:
FunctionEnd
Function un.onInit
    IfFileExists "$INSTDIR\.swirl-install-owned" 0 unowned_install
    StrCpy $IsolatedInstall "0"
    IfFileExists "$INSTDIR\.swirl-isolated-install" 0 +2
    StrCpy $IsolatedInstall "1"
    StrCmp $IsolatedInstall "1" 0 uninstall_ready
    !insertmacro ValidateIsolatedDirectory
    Goto uninstall_ready
    unowned_install:
    StrCpy $FailurePhase "ownership-marker"
    StrCpy $FailureCode "missing-payload"
    !insertmacro EmitFailureReceipt UNINSTALL
    SetErrorLevel 2
    Abort "缺少 Swirl 安装标记，停止卸载以保留目录内容。"
    uninstall_ready:
FunctionEnd
Section "安装 Swirl"
    SetShellVarContext current
    StrCmp $IsolatedInstall "1" 0 directory_ready
    !insertmacro ValidateIsolatedDirectory
    IfFileExists "$INSTDIR\*.*" 0 directory_ready
    IfFileExists "$INSTDIR\.swirl-isolated-install" directory_ready
    SetErrorLevel 2
    Abort "隔离验证目录已有未标记文件，请使用新的测试目录。"
    directory_ready:
    ; Replace the previous build in the same directory, without deleting data.
    ; Do not silently leave a running executable from the previous version.
    check_running:
    IfFileExists "$INSTDIR\Swirl.exe" 0 ready_to_copy
    StrCpy $FailurePhase "gui-write-open"
    System::Call 'kernel32::CreateFileW(w "$INSTDIR\Swirl.exe", i 0x40000000, i 1, p 0, i 3, i 0, p 0) p.r0 ?e'
    Pop $FailureCode
    StrCmp $0 "-1" blocked ready_close
    ready_close:
    System::Call 'kernel32::CloseHandle(p r0)'
    Goto ready_to_copy
    blocked:
    IfSilent installation_failed
    MessageBox MB_RETRYCANCEL|MB_ICONINFORMATION "请先完全退出 Swirl，再点击重试。支持托盘的版本请在右下角图标菜单选择「退出 Swirl」。安装程序会覆盖更新，保留您的配置和数据。" IDRETRY check_running IDCANCEL installation_failed
    ready_to_copy:
    !insertmacro PreparePackageMaintenance
    !insertmacro MaintainPackage Upgrade '-PrepareOnly -PreviousManifest "$PLUGINSDIR\previous-package-manifest.json"' installation_failed
    !insertmacro RequireNativeTunRecovery installation_failed
    SetOverwrite on
    ClearErrors
    StrCpy $FailurePhase "payload-copy"
    StrCpy $FailureCode "unavailable"
    SetOutPath "$INSTDIR"
    File /r "${APP_DIST}\\*.*"
    IfErrors installation_failed
    !insertmacro MaintainPackage Verify '' installation_failed
    !insertmacro MaintainPackage Upgrade '-PreviousManifest "$PLUGINSDIR\previous-package-manifest.json"' installation_failed
    WriteUninstaller "$INSTDIR\\卸载 Swirl.exe"
    FileOpen $0 "$INSTDIR\.swirl-install-owned" w
    FileWrite $0 "Swirl verified package installation."
    FileClose $0
    StrCmp $IsolatedInstall "1" isolated regular
    isolated:
    FileOpen $0 "$INSTDIR\.swirl-isolated-install" w
    FileWrite $0 "Isolated deployment validation; no registry or shortcut changes."
    FileClose $0
    Goto install_done
    regular:
    ; The embedded source-bound helper owns the complete per-user transaction:
    ; raw original types/bytes, compare-before-restore and user-edit retention.
    !insertmacro MaintainUserIntegration Install installation_failed
    install_done:
    Goto installation_finished
    installation_failed:
    !insertmacro EmitFailureReceipt INSTALL
    SetErrorLevel 2
    Abort "Swirl 正在运行、TUN 恢复未确认或文件无法写入，更新未完成。请保留现有恢复文件后重试。"
    installation_finished:
SectionEnd
Section "Uninstall"
    SetShellVarContext current
    uninstall_check_running:
    IfFileExists "$INSTDIR\Swirl.exe" 0 uninstall_gui_stopped
    StrCpy $FailurePhase "gui-write-open"
    System::Call 'kernel32::CreateFileW(w "$INSTDIR\Swirl.exe", i 0x40000000, i 1, p 0, i 3, i 0, p 0) p.r0 ?e'
    Pop $FailureCode
    StrCmp $0 "-1" uninstall_running
    System::Call 'kernel32::CloseHandle(p r0)'
    Goto uninstall_gui_stopped
    uninstall_running:
    IfSilent uninstall_failed
    MessageBox MB_RETRYCANCEL|MB_ICONINFORMATION "请先完全退出 Swirl 并等待网络恢复，再点击重试。支持托盘的版本请在右下角图标菜单选择「退出 Swirl」。" IDRETRY uninstall_check_running IDCANCEL uninstall_failed
    uninstall_gui_stopped:
    !insertmacro PreparePackageMaintenance
    !insertmacro RequireNativeTunRecovery uninstall_failed
    StrCmp $IsolatedInstall "1" integration_validated
    !insertmacro MaintainUserIntegration ValidateUninstall uninstall_failed
    ; Preserve the source manifest and product bytes if a locked or otherwise
    ; unavailable integration target needs a later restoration retry.
    !insertmacro MaintainUserIntegration Uninstall uninstall_failed
    integration_validated:
    !insertmacro MaintainPackage Uninstall '' uninstall_failed
    StrCmp $IsolatedInstall "1" isolated_uninstall
    Delete "$INSTDIR\.swirl-user-integration.json"
    isolated_uninstall:
    ; The embedded helper removed only unchanged files owned by this build.
    Delete "$INSTDIR\.swirl-isolated-install"
    Delete "$INSTDIR\.swirl-install-owned"
    Delete "$INSTDIR\卸载 Swirl.exe"
    RMDir "$INSTDIR"
    Goto uninstall_finished
    uninstall_failed:
    !insertmacro EmitFailureReceipt UNINSTALL
    SetErrorLevel 2
    Abort "网络恢复、安装文件归属或路径未能确认安全，卸载已停止。请保留现有文件后重试。"
    uninstall_finished:
SectionEnd
