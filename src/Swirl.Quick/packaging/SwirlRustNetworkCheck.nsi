; Dedicated installer for the Rust network acceptance preview.
; This does not replace the ordinary Swirl installation or change network settings.
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
!ifndef ENGINE_SHA
!error "ENGINE_SHA is required"
!endif
!ifndef INSTALL_README
!error "INSTALL_README is required"
!endif

Var IsolatedInstall
Var Parameters

!define MUI_ABORTWARNING
Name "Swirl Rust 联网测试"
OutFile "${OUT_DIR}\Swirl-Rust-Network-Check-Setup-${SOURCE_SHORT}.exe"
InstallDir "D:\Codex\SwirlRustCheck"
RequestExecutionLevel user
ShowInstDetails show
ShowUnInstDetails show
VIProductVersion "0.1.0.0"
VIAddVersionKey /LANG=2052 "ProductName" "Swirl Rust 联网测试"
VIAddVersionKey /LANG=2052 "FileDescription" "Swirl Rust 联网测试安装程序"
VIAddVersionKey /LANG=2052 "ProductVersion" "0.1.0.0"
VIAddVersionKey /LANG=2052 "Comments" "Engine source ${ENGINE_SHA}"

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

Section "安装联网测试"
    SetShellVarContext current
    ; The fixed, short D: path prevents Explorer's long-path ZIP extraction error.
    StrCmp $INSTDIR "D:\Codex\SwirlRustCheck" install_path_ok
    Abort "此测试版只安装到 D:\Codex\SwirlRustCheck。"
    install_path_ok:
    IfFileExists "$INSTDIR\*.*" existing_contents copy_files
    existing_contents:
    IfFileExists "$INSTDIR\.swirl-rust-check-owned" copy_files
    Abort "安装目录已有其他文件，请不要覆盖。"
    copy_files:
    SetOutPath "$INSTDIR"
    SetOverwrite on
    ClearErrors
    File /r "${APP_DIST}\*.*"
    IfErrors install_failed
    File /oname=README-安装后先看.txt "${INSTALL_README}"
    IfErrors install_failed
    WriteUninstaller "$INSTDIR\Uninstall-SwirlRustCheck.exe"
    IfErrors install_failed
    FileOpen $0 "$INSTDIR\.swirl-rust-check-owned" w
    IfErrors install_failed
    FileWrite $0 "Swirl Rust acceptance preview; engine ${ENGINE_SHA}"
    FileClose $0
    StrCmp $IsolatedInstall "1" isolated_install regular_install
    isolated_install:
    FileOpen $0 "$INSTDIR\.swirl-rust-check-isolated" w
    FileClose $0
    Goto install_done
    regular_install:
    Delete "$INSTDIR\.swirl-rust-check-isolated"
    CreateDirectory "$SMPROGRAMS\Swirl Rust 联网测试"
    CreateShortCut "$SMPROGRAMS\Swirl Rust 联网测试\运行联网测试.lnk" "$INSTDIR\TEST-SWIRL-NETWORK.cmd" "" "$INSTDIR\Swirl.exe" 0
    CreateShortCut "$DESKTOP\Swirl Rust 联网测试.lnk" "$INSTDIR\TEST-SWIRL-NETWORK.cmd" "" "$INSTDIR\Swirl.exe" 0
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustNetworkCheck" "DisplayName" "Swirl Rust 联网测试"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustNetworkCheck" "DisplayVersion" "0.1.0.0"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustNetworkCheck" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustNetworkCheck" "DisplayIcon" "$INSTDIR\Swirl.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustNetworkCheck" "UninstallString" '"$INSTDIR\Uninstall-SwirlRustCheck.exe"'
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustNetworkCheck" "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustNetworkCheck" "NoRepair" 1
    install_done:
    Goto install_finished
    install_failed:
    SetErrorLevel 2
    Abort "安装文件复制失败。"
    install_finished:
SectionEnd

Function un.onInit
    StrCmp $INSTDIR "D:\Codex\SwirlRustCheck" uninstall_path_ok
    Abort "卸载位置不是此测试版的固定目录。"
    uninstall_path_ok:
    IfFileExists "$INSTDIR\.swirl-rust-check-owned" uninstall_owned
    Abort "缺少此测试版的目录标记，停止卸载。"
    uninstall_owned:
FunctionEnd

Section "Uninstall"
    SetShellVarContext current
    IfFileExists "$INSTDIR\.swirl-rust-check-isolated" isolated_uninstall regular_uninstall
    regular_uninstall:
    Delete "$DESKTOP\Swirl Rust 联网测试.lnk"
    Delete "$SMPROGRAMS\Swirl Rust 联网测试\运行联网测试.lnk"
    RMDir "$SMPROGRAMS\Swirl Rust 联网测试"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SwirlRustNetworkCheck"
    isolated_uninstall:
    !include "${UNINSTALL_LIST}"
    Delete "$INSTDIR\README-安装后先看.txt"
    Delete "$INSTDIR\Uninstall-SwirlRustCheck.exe"
    Delete "$INSTDIR\.swirl-rust-check-isolated"
    Delete "$INSTDIR\.swirl-rust-check-owned"
    RMDir "$INSTDIR"
SectionEnd
