; Instalador do Gestor de Evidencias (Inno Setup 6).
;
; Gerado pelo compilar.bat depois do PyInstaller; sai em dist\GestorEvidencias-Setup.exe.
; Para gerar a mao:  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" instalador.iss
;
; Decisoes:
; - Instala so para o usuario atual ({autopf} vira %LOCALAPPDATA%\Programs), sem
;   pedir administrador: funciona em PC corporativo sem permissao de admin.
; - O atalho do menu Iniciar e a chave de "Iniciar com o Windows" usam o MESMO
;   nome e lugar que o app usa (gestor\sistema\startup.py). Assim as caixas de
;   Configuracoes mostram o que o instalador fez, e nao nasce atalho duplicado.
; - Capturas e config.json (%APPDATA%\GestorEvidencias) nao sao tocados nem na
;   atualizacao nem na desinstalacao: sao evidencias do usuario.

#define AppNome "Gestor de Evidencias"
#define AppExe "GestorEvidencias.exe"
; versao pela data da compilacao: o projeto nao tem numero de versao proprio
#define AppVersao GetDateTimeString('yyyy.mm.dd', '.', '')

[Setup]
; Nao trocar o AppId: e por ele que o Windows reconhece a atualizacao como o
; mesmo programa (instala por cima em vez de criar um segundo).
AppId={{87B5C318-B319-4F8E-BA56-B7C22E9AA1AB}
AppName={#AppNome}
AppVersion={#AppVersao}
AppVerName={#AppNome} {#AppVersao}
AppPublisher=Dassayani
AppPublisherURL=https://github.com/dassayani/gestordeevidencias
PrivilegesRequired=lowest
DefaultDirName={autopf}\GestorEvidencias
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=dist
OutputBaseFilename=GestorEvidencias-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppNome}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Com o app aberto, a atualizacao e a desinstalacao pedem para fechar antes
; (mesmo mutex da trava de instancia unica, gestor\sistema\instancia.py).
AppMutex=GestorEvidencias.Instancia
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "iniciar"; Description: "Iniciar com o Windows (o Print Screen funciona logo depois do login)"
Name: "desktop"; Description: "Criar atalho na Área de Trabalho"; Flags: unchecked

[InstallDelete]
; Na atualizacao, sobra de bibliotecas da versao anterior nao fica misturada
; com as novas.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\GestorEvidencias\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppNome}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Comment: "Gestor de Evidencias - capturas de tela para evidencia"
Name: "{userdesktop}\{#AppNome}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktop

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "GestorEvidencias"; ValueData: """{app}\{#AppExe}"""; Tasks: iniciar; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir o {#AppNome} agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; atalho criado pelo proprio app em Configuracoes (mesmo caminho do [Icons])
Type: files; Name: "{userprograms}\{#AppNome}.lnk"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // "Iniciar com o Windows" ligado depois, por Configuracoes, nao passa pelo
  // [Registry]; sem isto o Windows tentaria abrir no login um exe que nao existe
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'GestorEvidencias');
end;
