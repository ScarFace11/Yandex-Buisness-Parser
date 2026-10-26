# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Yandex Business Parser (Windows).
#
# Build (публичная сборка):  pyinstaller parser.spec
# Result: dist/YandexBusinessParser/YandexBusinessParser.exe  (onedir —
# starts fast and trips fewer antivirus false positives than onefile).
#
# Playwright НЕ bundles: приложение работает через Chrome DevTools Protocol
# с Google Chrome, установленным в системе. Встроенный Chromium (~300 МБ)
# и его автоматизация оставляли узнаваемый след, поэтому Playwright и
# curl_cffi исключены из сборки — как и любые прямые HTTP-запросы к Картам.

import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

APP_NAME = "YandexBusinessParser"
# Фирменная иконка .exe: в проводнике, на ярлыке и в панели задач.
ICON = os.path.join("static", "icon.ico")
if not os.path.exists(ICON):
    ICON = None

a = Analysis(
    ['app.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=[
        # Read-only resources served by Flask
        ('templates', 'templates'),
        ('static', 'static'),
        # Тексты обновлений: «Что нового» и подпись баннера читаются с диска.
        ('update_notes/notes', 'update_notes/notes'),
        ('update_notes/ui.json', 'update_notes'),
    ],
    hiddenimports=(
        # Search/enrichment pipeline modules are imported dynamically
        # inside runner.run_web — make sure they are bundled.
        collect_submodules('yandex_maps_parser')
        + collect_submodules('routes')
        + [
            'run_manager',
            'run_logger',
            'search_history',
            # app.py --check: самопроверка без интерфейса
            'selfcheck',
            # app.py --run: сбор по пресету без интерфейса
            'headless',
            'presets_store',
            'paths',
            'console_io',
            # app.py --apply-update: помощник ставит файлы после выхода
            'updater_helper',
            'update_notes',
            # multiprocessing children re-import the entry module
            '__main__',
        ]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Not needed at runtime, cuts ~100+ MB combined
        'tkinter',
        'pytest',
        'matplotlib',
        'numpy',
        'PIL',
        'IPython',
        'jedi',
        # Убрано из приложения: страницы читает только настоящий Chrome.
        'playwright',
        'greenlet',
        'curl_cffi',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    icon=ICON,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # server log stays visible; browser opens manually
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)
