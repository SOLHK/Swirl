; Normal Swirl UI with the in-process Rust core. It installs beside existing Swirl.
; The installer does not run the app or change Windows network settings.
; NSIS reference: https://nsis.sourceforge.io/Docs/Chapter4.html
!include "MUI2.nsh"
!include "FileFunc.nsh"
Unicode true
SetCompressor /SOLID zlib

!ifndef APP_DIST
!error "APP_DIST is required"
!endif
!ifndef OUT_DIR
!error "OUT_DIR is required"
!endif
!ifndef UNINSTALL_LIST
!error "UNINSTALL_LIST is required"
!endif
!ifndef SOURCE_SHORT
!error "SOURCE_SHORT is required"
!endif
!ifndef SOURCE_SHA
!error "SOURCE_SHA is required"
!endif

Var IsolatedInstall
Var Parameters
!define MUI_ABORTWARNING
Name "Swirl Rust Core（预览版）"
OutFile "${OUT_DIR}\Swirl-Rust-Core-Setup-${SOURCE_SHORT}.exe"
InstallDir "D:\Codex\SwirlRust"
RequestExecutionLevel user
ShowInstDetails show
ShowUnInstDetails show
VIProductVersion "0.1.0.0"
VIAddVersionKey /LANG=2052 "ProductName" "Swirl Rust Core 预览版"
VIAddVersionKey /LANG=2052 "FileDescription" "Swirl Rust Core 应用安装程序"
VIAddVersionKey /LANG=2052 "ProductVersion" "0.1.0.0"
VIAddVersionKey /LANG=2052 "Comments" "Source ${SOURCE_SHA}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Function .onInit
    StrCpy $IsolatedInstall "0"
    ${GetParameters} $Parameters
    ClearErrors
    ${GetOptions} $Parameters "/ISOLATED" $0
    IfErrors init_done
    StrCpy $IsolatedInstall "1"
    init_done:
FunctionEnd

Section "安装 Swirl Rust Core"
    SetShellVarContext current
    ; Keep the app separate from the user's working Mihomo-backed Swirl.
    StrCmp $INSTDIR "D:\Codex\SwirlRust" install_path_ok
    Abort "此 Rust 预览版只安装到 D:\Codex\SwirlRust。"
    install_path_ok:
    IfFileExists "$INSTDIR\*.*" existing_contents copy_files
    existing_contents:
    IfFileExists "$INSTDIR\.swirl-rust-app-owned" copy_files
    Abort "安装目录已有其他文件，请不要覆盖。"
    copy_files:
    SetOutPath "$INSTDIR"
    SetOverwrite on
    ClearErrors
    File /r "${APP_DIST}\*.*"
    IfErrors install_failed
    WriteUninstaller "$INSTDIR\Uninstall-SwirlRust.exe"
    IfErrors install_failed
    FileOpen $0 "$INSTDIR\.swirl-rust-app-owned" w
    IfErrors install_failed
    FileWrite $0 "Swirl Rust Core preview; source ${SOURCE_SHA}"
    FileClose $0
    StrCmp $IsolatedInstall "1" isolated_install regular_install
    isolated_install:
    FileOpen $0 "$INSTDIR\.swirl-rust-app-isolated" w
    FileClose $0
    Goto install_done
    regular_install:
    Delete "$INSTDIR\.swirl-rust-app-isolated"
    CreateDirectory "$SMPROGRAMS\Swirl Rust Core"
    CreateShortCut "$SMPROGRAMS\Swirl Rust Core\Swirl Rust Core.lnk" "$INSTDIR\Swirl.exe" "" "$INSTDIR\Swirl.exe" 0
    CreateShortCut "$DESKTOP\Swirl Rust Core.lnk" "$INSTDIR\Swirl.exe" "" "$INSTDIR\Swirl.exe" 0
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustCorePreview" "DisplayName" "Swirl Rust Core（预览版）"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustCorePreview" "DisplayVersion" "0.1.0.0"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustCorePreview" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustCorePreview" "DisplayIcon" "$INSTDIR\Swirl.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustCorePreview" "UninstallString" '"$INSTDIR\Uninstall-SwirlRust.exe"'
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustCorePreview" "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustCorePreview" "NoRepair" 1
    install_done:
    Goto install_finished
    install_failed:
    SetErrorLevel 2
    Abort "应用文件复制失败；未修改网络设置。"
    install_finished:
SectionEnd

Function un.onInit
    StrCmp $INSTDIR "D:\Codex\SwirlRust" uninstall_path_ok
    Abort "卸载位置不是此 Rust 预览版的固定目录。"
    uninstall_path_ok:
    IfFileExists "$INSTDIR\.swirl-rust-app-owned" uninstall_owned
    Abort "缺少此 Rust 预览版的目录标记，停止卸载。"
    uninstall_owned:
FunctionEnd

Section "Uninstall"
    SetShellVarContext current
    IfFileExists "$INSTDIR\.swirl-rust-app-isolated" isolated_uninstall regular_uninstall
    regular_uninstall:
    Delete "$DESKTOP\Swirl Rust Core.lnk"
    Delete "$SMPROGRAMS\Swirl Rust Core\Swirl Rust Core.lnk"
    RMDir "$SMPROGRAMS\Swirl Rust Core"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustCorePreview"
    isolated_uninstall:
    !include "${UNINSTALL_LIST}"
    Delete "$INSTDIR\Uninstall-SwirlRust.exe"
    Delete "$INSTDIR\.swirl-rust-app-isolated"
    Delete "$INSTDIR\.swirl-rust-app-owned"
    RMDir "$INSTDIR"
SectionEnd
