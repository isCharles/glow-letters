#define AppName "Glow Letters"
#define AppVersion "0.1.1"
#define AppPublisher "isCharles"
#define AppExe "GlowLetters.exe"
#ifndef AppDist
  #define AppDist "..\dist\GlowLetters"
#endif

[Setup]
AppId={{E94A912D-E437-47E4-9F84-8A28E73CDF3E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\Glow Letters
DefaultGroupName=Glow Letters
OutputDir=..\release
OutputBaseFilename=GlowLetters-{#AppVersion}-Windows-x64-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "daily"; Description: "Daily glow notifications at 15:00 and 21:00 / 每天 15:00、21:00 消息通知"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut / 创建桌面快捷方式"; Flags: unchecked

[Files]
Source: "{#AppDist}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "tasks.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\CITY-GEO-LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Glow Letters"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\Glow Letters"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\glowletters"; ValueType: string; ValueName: ""; ValueData: "URL:Glow Letters"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\glowletters"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\glowletters\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" --open-url ""%1"""

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tasks.ps1"" -Mode Install -ExePath ""{app}\{#AppExe}"""; Flags: runhidden waituntilterminated; Check: WizardIsTaskSelected('daily')
Filename: "{app}\{#AppExe}"; Description: "Launch Glow Letters / 打开霞光来信"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tasks.ps1"" -Mode Uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveGlowLettersTasks"
