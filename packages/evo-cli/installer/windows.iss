; Inno Setup definition for the evo-cli Windows installer.
;
; Built via packages/evo-cli/scripts/build_windows_installer.ps1, which
; invokes ISCC.exe with:
;   /DAppVersion=<version>              (required)
;   /DSourceDir=<pyinstaller dist dir>  (required)
;   /DSIGN=1 /Ssigntool=<command>       (only when a signing certificate is configured)
;
; Do not change AppId across releases - it identifies upgrades for existing
; installs.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\..\dist\pyinstaller\evo"
#endif

[Setup]
AppId={{ED45E4AF-6625-405C-ACA5-A57A14EE5C69}}
AppName=Evo CLI
AppVersion={#AppVersion}
AppPublisher=Seequent
AppPublisherURL=https://www.seequent.com/
DefaultDirName={localappdata}\Programs\EvoCLI
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ChangesEnvironment=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\..\release
OutputBaseFilename=evo-cli-{#AppVersion}-setup-windows-x64
Compression=lzma2
SolidCompression=yes
#ifdef SIGN
SignTool=signtool
SignedUninstaller=yes
#endif

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Code]
const
  EnvironmentKey = 'Environment';

function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;

procedure EnvAddPath(Path: string);
var
  Paths: string;
begin
  if not NeedsAddPath(Path) then
    exit;

  if not RegQueryStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths) then
    Paths := '';

  if (Length(Paths) > 0) and (Paths[Length(Paths)] <> ';') then
    Paths := Paths + ';';
  Paths := Paths + Path;

  RegWriteExpandStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths);
end;

procedure EnvRemovePath(Path: string);
var
  Paths, NewPaths, Part: string;
  P: Integer;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths) then
    exit;

  NewPaths := '';
  while Length(Paths) > 0 do
  begin
    P := Pos(';', Paths);
    if P = 0 then
    begin
      Part := Paths;
      Paths := '';
    end
    else
    begin
      Part := Copy(Paths, 1, P - 1);
      Paths := Copy(Paths, P + 1, Length(Paths));
    end;

    if (Length(Part) > 0) and (Uppercase(Part) <> Uppercase(Path)) then
    begin
      if Length(NewPaths) > 0 then
        NewPaths := NewPaths + ';';
      NewPaths := NewPaths + Part;
    end;
  end;

  RegWriteExpandStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', NewPaths);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    EnvAddPath(ExpandConstant('{app}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    EnvRemovePath(ExpandConstant('{app}'));
end;
