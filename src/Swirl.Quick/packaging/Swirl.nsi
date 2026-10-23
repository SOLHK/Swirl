!include "MUI2.nsh"
!include "FileFunc.nsh"
Unicode true
SetCompressor /SOLID lzma
Var IsolatedInstall
Var Parameters
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
    File /oname=Maintain-WindowsRustProduct.ps1 "${__FILEDIR__}\..\..\..\scripts\Maintain-WindowsRustProduct.ps1"
    File /oname=RustProductPackagePolicy.ps1 "${__FILEDIR__}\..\..\..\scripts\RustProductPackagePolicy.ps1"
    File /oname=package-manifest.json "${APP_DIST}\package-manifest.json"
!macroend
!macro MaintainPackage Mode ExtraArguments FailureLabel
    nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "$PLUGINSDIR\Maintain-WindowsRustProduct.ps1" -Mode ${Mode} -ApplicationDirectory "$INSTDIR" -ExpectedManifest "$PLUGINSDIR\package-manifest.json" ${ExtraArguments}'
    Pop $0
    Pop $1
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
    System::Call 'kernel32::CreateFileW(w "$INSTDIR\Swirl.exe", i 0x40000000, i 1, p 0, i 3, i 0, p 0) p.r0'
    StrCmp $0 "-1" blocked ready_close
    ready_close:
    System::Call 'kernel32::CloseHandle(p r0)'
    Goto ready_to_copy
    blocked:
    IfSilent installation_failed
    MessageBox MB_RETRYCANCEL|MB_ICONINFORMATION "请先退出 Swirl，再点击重试。安装程序会覆盖更新，保留您的配置和数据。" IDRETRY check_running IDCANCEL installation_failed
    ready_to_copy:
    !insertmacro PreparePackageMaintenance
    !insertmacro MaintainPackage Upgrade '-PrepareOnly -PreviousManifest "$PLUGINSDIR\previous-package-manifest.json"' installation_failed
    SetOverwrite on
    ClearErrors
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
    CreateDirectory "$SMPROGRAMS\\Swirl"
    CreateShortCut "$SMPROGRAMS\\Swirl\\Swirl.lnk" "$INSTDIR\\Swirl.exe" "" "$INSTDIR\\Swirl-brand-phase3-v2.ico" 0
    !if /FileExists "${APP_DIST}\SwirlCodexLauncher.exe"
    CreateShortCut "$SMPROGRAMS\\Swirl\\通过 Swirl 启动 Codex.lnk" "$INSTDIR\\SwirlCodexLauncher.exe" "" "$INSTDIR\\Swirl-brand-phase3-v2.ico" 0
    !endif
    CreateShortCut "$DESKTOP\\Swirl.lnk" "$INSTDIR\\Swirl.exe" "" "$INSTDIR\\Swirl-brand-phase3-v2.ico" 0
    ExecWait '"$INSTDIR\SwirlProxyGuard.exe" --repair-shortcut "$DESKTOP\Swirl.lnk" "$INSTDIR\Swirl.exe" "$INSTDIR\Swirl-brand-phase3-v2.ico"' $0
    StrCmp $0 0 +2
    DetailPrint "Swirl 桌面快捷方式属性更新失败，错误 $0。"
    ExecWait '"$INSTDIR\SwirlProxyGuard.exe" --repair-shortcut "$SMPROGRAMS\Swirl\Swirl.lnk" "$INSTDIR\Swirl.exe" "$INSTDIR\Swirl-brand-phase3-v2.ico"' $0
    StrCmp $0 0 +2
    DetailPrint "Swirl 开始菜单快捷方式属性更新失败，错误 $0。"
    WriteRegStr HKCU "Software\\Swirl" "InstallDir" "$INSTDIR"
    ExecWait '"$INSTDIR\SwirlProxyGuard.exe" --repair-owned-pins "$INSTDIR\Swirl.exe" "$INSTDIR\Swirl-brand-phase3-v2.ico"' $0
    StrCmp $0 0 +2
    DetailPrint "Swirl 任务栏图标刷新未完成，错误 $0。"
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "DisplayName" "Swirl"
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "DisplayVersion" "${APP_VERSION}.0"
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "UninstallString" '"$INSTDIR\\卸载 Swirl.exe"'
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "DisplayIcon" "$INSTDIR\\Swirl-brand-phase3-v2.ico"
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "Publisher" "Swirl"
    WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "NoModify" 1
    WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "NoRepair" 1
    install_done:
    Goto installation_finished
    installation_failed:
    SetErrorLevel 2
    Abort "Swirl 正在运行或文件无法写入，更新未完成。"
    installation_finished:
SectionEnd
Section "Uninstall"
    SetShellVarContext current
    !insertmacro PreparePackageMaintenance
    !insertmacro MaintainPackage Uninstall '' uninstall_failed
    StrCmp $IsolatedInstall "1" isolated_uninstall
    Delete "$DESKTOP\\Swirl.lnk"
    Delete "$SMPROGRAMS\\Swirl\\Swirl.lnk"
    Delete "$SMPROGRAMS\\Swirl\\通过 Swirl 启动 Codex.lnk"
    RMDir "$SMPROGRAMS\\Swirl"
    DeleteRegKey HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl"
    DeleteRegKey HKCU "Software\\Swirl"
    isolated_uninstall:
    ; The embedded helper removed only unchanged files owned by this build.
    Delete "$INSTDIR\.swirl-isolated-install"
    Delete "$INSTDIR\.swirl-install-owned"
    Delete "$INSTDIR\卸载 Swirl.exe"
    RMDir "$INSTDIR"
    Goto uninstall_finished
    uninstall_failed:
    SetErrorLevel 2
    Abort "安装文件归属或路径验证失败，卸载未完成。您的未验证文件已保留。"
    uninstall_finished:
SectionEnd
