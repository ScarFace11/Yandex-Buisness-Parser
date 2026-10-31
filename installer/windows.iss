; Установщик Windows для Яндекс Бизнес Парсера.
;
; Сборка (из корня репозитория, после pyinstaller parser.spec):
;   iscc /DMyAppVersion=2.3.5 installer\windows.iss
;
; Установка — per-user, без запроса администратора:
;   программа  → %LOCALAPPDATA%\Programs\YandexBusinessParser
;   данные     → %APPDATA%\YandexBusinessParser (output, logs, .env, settings)
;   ярлыки     → меню «Пуск» и рабочий стол
;
; Portable-режим не ломается: zip-сборка не содержит метки .installed и
; по-прежнему хранит данные рядом с exe. Если рядом с exe лежит .portable,
; даже установленная копия работает как portable (см. paths.data_dir).
#ifndef MyAppVersion
  #define MyAppVersion "2.3.5"
#endif
#define MyAppName "Яндекс Бизнес Парсер"
#define MyAppShortName "YandexBusinessParser"
#define MyAppExeName "YandexBusinessParser.exe"
#define MyAppPublisher "Yandex Business Parser"
#define MyAppURL "https://github.com/ScarFace11/Yandex-Buisness-Parser"
#define BuildDir "..\dist\YandexBusinessParser"
[Setup]
AppId={{8B7F4C62-2D1E-4A7B-9E44-2B7D5B6C1A90}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\{#MyAppShortName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename={#MyAppShortName}-windows-x64-setup
SetupIconFile=..\static\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
UsePreviousAppDir=yes
AllowNoIcons=yes
[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; \
    GroupDescription: "Дополнительно:"; Flags: checkedonce
[Files]
; Только файлы сборки. Данные пользователя (output, logs, .env, settings.json)
; и служебные метки в установщик не попадают.
Source: "{#BuildDir}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs; \
    Excludes: ".local-build,.portable,portable.txt,.env,settings.json,sender_config.json,output\*,logs\*,_update\*"
[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    WorkingDir: "{app}"; Comment: "Поиск клиентов на Яндекс.Картах"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    WorkingDir: "{app}"; Tasks: desktopicon
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent
[UninstallDelete]
; Приложение умеет обновлять себя и добавлять файлы, которых нет в списке
; установщика. Удаляем всю папку программы; данные в %APPDATA% не трогаем —
; их удаление спрашивается отдельно в [Code].
Type: filesandordirs; Name: "{app}"
[Code]
const
  DataDirName = 'YandexBusinessParser';
procedure CurStepChanged(CurStep: TSetupStep);
var
  Marker: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Метка установленной копии: paths.data_dir() уводит данные в AppData.
    Marker := ExpandConstant('{app}\.installed');
    SaveStringToFile(Marker, 'installed' + #13#10, False);
    // Если папку установки случайно собрали из portable-копии, явные метки
    // portable убираем: иначе установленная программа осталась бы portable.
    DeleteFile(ExpandConstant('{app}\.portable'));
    DeleteFile(ExpandConstant('{app}\portable.txt'));
  end;
end;
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Метка portable внутри установленной копии: данные лежат в {app}, и
    // [UninstallDelete] снёс бы их вместе с программой. Предупреждаем и
    // даём отменить удаление, чтобы успеть скопировать файлы.
    if FileExists(ExpandConstant('{app}\.portable')) or
       FileExists(ExpandConstant('{app}\portable.txt')) then
      if MsgBox('Приложение работает в portable-режиме: результаты, история ' +
                'и ключи лежат в папке программы и будут удалены вместе с ней.' +
                Chr(13) + Chr(10) + Chr(13) + Chr(10) +
                'Отменить удаление, чтобы сохранить данные?',
                mbConfirmation, MB_YESNO) = IDYES then
        Abort;
    DataDir := ExpandConstant('{userappdata}\' + DataDirName);
    if DirExists(DataDir) then
      if MsgBox('Удалить также ваши данные?' + #13#10#13#10 +
                'Это результаты поисков, история, шаблоны, настройки и ключи.' + #13#10 +
                'Папка: ' + DataDir + #13#10#13#10 +
                'Нет — данные останутся, и их можно будет использовать после ' +
                'повторной установки.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
