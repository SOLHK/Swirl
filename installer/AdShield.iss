; Swirl Windows x64 setup, built by GitHub Actions using Inno Setup 6.
#define AppName "Swirl"
#define AppVersion "0.7.2"
#define AppExe "Swirl.exe"

[Setup]
AppId={{79175CC7-CA2F-447D-87F0-E66B1747951B}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=SOLHK
DefaultDirName={autopf}\Swirl
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=..\AdShield\Assets\swirl.ico
OutputDir=..\dist
OutputBaseFilename=Swirl_Setup_{#AppVersion}_x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
MinVersion=10.0.19041

[Languages]
Name: "chinesesimp"; MessagesFile: ".\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce

[Files]
Source: "..\publish\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Swirl"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\swirl-glass-070.ico"
Name: "{group}\卸载 Swirl"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Swirl"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\swirl-glass-070.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即启动 Swirl"; Flags: nowait postinstall skipifsilent
