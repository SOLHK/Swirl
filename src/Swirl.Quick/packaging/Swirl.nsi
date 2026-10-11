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
!define MUI_ABORTWARNING
!define MUI_ICON "../assets/swirl.ico"
!define MUI_UNICON "../assets/swirl.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\\Swirl.exe"
!define MUI_FINISHPAGE_RUN_TEXT "启动 Swirl"
Name "Swirl"
OutFile "${OUT_DIR}\\Swirl-Setup.exe"
InstallDir "$LOCALAPPDATA\\Programs\\Swirl"
InstallDirRegKey HKCU "Software\\Swirl" "InstallDir"
RequestExecutionLevel user
ShowInstDetails show
ShowUnInstDetails show
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
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
    IfErrors +2 0
    StrCpy $IsolatedInstall "1"
FunctionEnd
Function un.onInit
    StrCpy $IsolatedInstall "0"
    IfFileExists "$INSTDIR\.swirl-isolated-install" 0 +2
    StrCpy $IsolatedInstall "1"
FunctionEnd
Section "安装 Swirl"
    SetShellVarContext current
    SetOutPath "$INSTDIR"
    File /r "${APP_DIST}\\*.*"
    WriteUninstaller "$INSTDIR\\卸载 Swirl.exe"
    StrCmp $IsolatedInstall "1" isolated regular
    isolated:
    FileOpen $0 "$INSTDIR\.swirl-isolated-install" w
    FileWrite $0 "Isolated deployment validation; no registry or shortcut changes."
    FileClose $0
    Goto install_done
    regular:
    CreateDirectory "$SMPROGRAMS\\Swirl"
    CreateShortCut "$SMPROGRAMS\\Swirl\\Swirl.lnk" "$INSTDIR\\Swirl.exe" "" "$INSTDIR\\Swirl-icon-flat.ico" 0
    CreateShortCut "$DESKTOP\\Swirl.lnk" "$INSTDIR\\Swirl.exe" "" "$INSTDIR\\Swirl-icon-flat.ico" 0
    WriteRegStr HKCU "Software\\Swirl" "InstallDir" "$INSTDIR"
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "DisplayName" "Swirl"
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "UninstallString" '"$INSTDIR\\卸载 Swirl.exe"'
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "DisplayIcon" "$INSTDIR\\Swirl-icon-flat.ico"
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "Publisher" "Swirl"
    WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "NoModify" 1
    WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "NoRepair" 1
    install_done:
SectionEnd
Section "Uninstall"
    SetShellVarContext current
    StrCmp $IsolatedInstall "1" isolated_uninstall
    Delete "$DESKTOP\\Swirl.lnk"
    Delete "$SMPROGRAMS\\Swirl\\Swirl.lnk"
    RMDir "$SMPROGRAMS\\Swirl"
    DeleteRegKey HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl"
    DeleteRegKey HKCU "Software\\Swirl"
    isolated_uninstall:
    RMDir /r "$INSTDIR"
SectionEnd
