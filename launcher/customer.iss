#ifndef BuildRoot
  #error BuildRoot is required
#endif
#ifndef ReleaseVersion
  #define ReleaseVersion "0.3.0-beta.1"
#endif
#ifdef SmokeTest
  #define SetupAppId "{{D0DA15E4-75F3-4D60-9F06-47BE9CBF52D8}"
  #define SetupAppName "SmartFlow AI Smoke Test"
  #define SetupFolder "SmartFlowAI-SmokeTest"
  #define SetupSuffix "-SmokeTest"
#else
  #define SetupAppId "{{F59A4A3B-A56E-4F73-80CC-B0874AA34D8E}"
  #define SetupAppName "SmartFlow AI"
  #define SetupFolder "SmartFlowAI"
  #define SetupSuffix ""
#endif
[Setup]
AppId={#SetupAppId}
AppName={#SetupAppName}
AppVersion={#ReleaseVersion}
AppPublisher=SmartFlow AI
DefaultDirName={localappdata}\Programs\{#SetupFolder}
DefaultGroupName={#SetupAppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#BuildRoot}
OutputBaseFilename=SmartFlow-AI-Setup-{#ReleaseVersion}{#SetupSuffix}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\SmartFlow AI.exe
CloseApplications=no
RestartApplications=no
DisableProgramGroupPage=yes
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "..\build\installer-tools\MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy noencryption
Source: "{#BuildRoot}\SmartFlow AI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#BuildRoot}\SmartFlow-Extension-*.zip"; DestDir: "{app}\extension-download"; Flags: ignoreversion
[Icons]
Name: "{group}\{#SetupAppName}"; Filename: "{app}\SmartFlow AI.exe"
Name: "{userdesktop}\{#SetupAppName}"; Filename: "{app}\SmartFlow AI.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\SmartFlow AI.exe"; Description: "Open SmartFlow AI"; Flags: nowait postinstall skipifsilent unchecked
[Code]
function HasWebViewAt(RootKey: Integer): Boolean;
var
  RuntimeVersion: String;
begin
  RuntimeVersion := '';
  Result := RegQueryStringValue(RootKey, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', RuntimeVersion) and
    (Trim(RuntimeVersion) <> '') and (RuntimeVersion <> '0.0.0.0');
end;

function NeedsWebView(): Boolean;
begin
  // Check each registration independently: an empty machine entry must not
  // mask a valid per-user Runtime. Edge browser alone is not this Runtime.
  Result := not (HasWebViewAt(HKLM32) or HasWebViewAt(HKCU));
end;

function InstallationRunning(): Boolean;
var
  Locator, Services, Processes, Process: Variant;
  Index: Integer;
  ExecutablePath, TargetPath: String;
  UnknownOwner: Boolean;
begin
  Result := False;
  UnknownOwner := False;
  TargetPath := ExpandFileName(ExpandConstant('{app}\SmartFlow AI.exe'));
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Services := Locator.ConnectServer('', 'root\CIMV2');
    Processes := Services.ExecQuery('SELECT ExecutablePath FROM Win32_Process WHERE Name="SmartFlow AI.exe"');
    for Index := 0 to Processes.Count - 1 do begin
      Process := Processes.ItemIndex(Index);
      try
        ExecutablePath := Process.ExecutablePath;
        if ExecutablePath = '' then
          UnknownOwner := True
        else if CompareText(ExpandFileName(ExecutablePath), TargetPath) = 0 then begin
          // Frozen shell and hidden --engine use the same executable. No
          // terminate/restart command is permitted during installer preflight.
          Result := True;
          Exit;
        end;
      except
        UnknownOwner := True;
      end;
    end;
  except
    UnknownOwner := True;
    Log('Could not inspect SmartFlow process ownership.');
  end;
  // If ownership is unavailable, preserve an existing installation rather
  // than replace potentially live files. A title in another installation must
  // not override a successful exact-path process scan.
  if FileExists(TargetPath) and UnknownOwner then begin
    if FindWindowByWindowName('SmartFlow AI — AI Clip Creator') <> 0 then
      Log('SmartFlow window present while process ownership is unavailable.');
    Result := True;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  if InstallationRunning() then begin
    Result := 'Please finish your jobs and close SmartFlow AI before updating this installation. Your work will not be removed.';
    Exit;
  end;
  if NeedsWebView() then begin
    try
      ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
      if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then begin
        Result := 'Could not start Microsoft WebView2 Runtime setup: ' + SysErrorMessage(ResultCode);
        Exit;
      end;
      if (ResultCode = 3010) or (ResultCode = 1641) then begin
        NeedsRestart := True;
        Result := 'Restart Windows to finish installing Microsoft WebView2 Runtime, then run SmartFlow Setup again.';
        Exit;
      end;
      if ResultCode <> 0 then begin
        Result := 'Microsoft WebView2 Runtime setup failed (code ' + IntToStr(ResultCode) + '). Check your internet connection, then retry Setup.';
        Exit;
      end;
      if NeedsWebView() then begin
        Result := 'Microsoft WebView2 Runtime is still unavailable. Install the official Evergreen Runtime, then retry Setup. SmartFlow files have not been replaced.';
        Exit;
      end;
    except
      Result := 'Could not install Microsoft WebView2 Runtime. Check your internet connection, then retry Setup. SmartFlow files have not been replaced.';
      Exit;
    end;
  end;
  // The bootstrapper may take time; recheck before replacing program files.
  if InstallationRunning() then begin
    Result := 'SmartFlow AI was opened during setup. Finish your jobs and close it before continuing.';
  end;
end;
