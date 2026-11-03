; Inno Setup script: a per-user Windows installer for Robot Framework Mind.
; CI compiles it with /DAppVersion=<version> after the Windows bundle is built.
; It installs under the user's local app data, so no administrator is needed.
#define AppName "Robot Framework Mind"
#define AppExe "robotframework-mind.exe"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8F1B2C3D-4E5F-4A6B-8C7D-9E0F1A2B3C4D}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=ai94iq
AppPublisherURL=https://github.com/ai94iq/robotframework-mind
AppSupportURL=https://github.com/ai94iq/robotframework-mind/issues
DefaultDirName={localappdata}\Programs\Robot Framework Mind
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\bundles
OutputBaseFilename=robotframework-mind-{#AppVersion}-windows-x64-setup
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\bundles\robotframework-mind-{#AppVersion}-windows-x64.exe"; DestDir: "{app}"; DestName: "{#AppExe}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
