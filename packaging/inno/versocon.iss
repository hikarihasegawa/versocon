; Inno Setup 6 — VersoCon (Windows installer)
; Compila: ISCC packaging\inno\versocon.iss

#define MyAppName      "VersoCon"
#define MyAppFullName  "VersoCon - Convertitore di File"
#define MyAppVersion   "0.2.5"
#define MyAppPublisher "hikari22"
#define MyAppURL       "https://ko-fi.com/hikari22"
#define MyAppExeName   "Versocon.exe"
#define MyKoFiURL      "https://ko-fi.com/hikari22"

[Setup]
AppId={{F3B8A1D7-3C4E-4F2B-9A5D-1C0E0A7B8C9D}}
AppName={#MyAppFullName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=versocon-setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=no
WizardStyle=modern
ShowLanguageDialog=no
SetupIconFile=..\versocon.ico
LicenseFile=..\..\LICENSE.md

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Crea icona su Desktop"; GroupDescription: "Icone:"; Flags: unchecked

[Files]
Source: "..\..\dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Supporta lo sviluppo (Ko-fi)"; Filename: "{#MyKoFiURL}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Avvia {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{tmp}\versocon"
