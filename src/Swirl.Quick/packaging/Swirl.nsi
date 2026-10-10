!include "MUI2.nsh"
Unicode true
!ifndef APP_DIST
!error "APP_DIST is required"
!endif
!ifndef OUT_DIR
!error "OUT_DIR is required"
!endif
!define MUI_ABORTWARNING
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
Section "安装 Swirl"
    SetShellVarContext current
    SetOutPath "$INSTDIR"
    File /r "${APP_DIST}\\*.*"
    CreateDirectory "$SMPROGRAMS\\Swirl"
    CreateShortCut "$SMPROGRAMS\\Swirl\\Swirl.lnk" "$INSTDIR\\Swirl.exe"
    CreateShortCut "$DESKTOP\\Swirl.lnk" "$INSTDIR\\Swirl.exe"
    WriteUninstaller "$INSTDIR\\卸载 Swirl.exe"
    WriteRegStr HKCU "Software\\Swirl" "InstallDir" "$INSTDIR"
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "DisplayName" "Swirl"
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "UninstallString" '"$INSTDIR\\卸载 Swirl.exe"'
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "DisplayIcon" "$INSTDIR\\Swirl.exe"
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "Publisher" "Swirl"
    WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "NoModify" 1
    WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl" "NoRepair" 1
SectionEnd
Section "Uninstall"
    SetShellVarContext current
    Delete "$DESKTOP\\Swirl.lnk"
    Delete "$SMPROGRAMS\\Swirl\\Swirl.lnk"
    RMDir "$SMPROGRAMS\\Swirl"
    RMDir /r "$INSTDIR"
    DeleteRegKey HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Swirl"
    DeleteRegKey HKCU "Software\\Swirl"
SectionEnd
