# -*- coding: utf-8 -*-
"""Установщик Windows и выбор папки данных: AppData или portable."""
from pathlib import Path

import paths

ROOT = Path(__file__).resolve().parent.parent
ISS = ROOT / "installer" / "windows.iss"
WF = ROOT / ".github" / "workflows" / "build-exe.yml"


class TestInstallerScript:
    def test_installer_is_per_user_and_keeps_portable_mode(self):
        text = ISS.read_text(encoding="utf-8")
        assert "PrivilegesRequired=lowest" in text
        assert "{localappdata}\\Programs" in text
        assert "{autoprograms}" in text and "{autodesktop}" in text
        assert "[UninstallDelete]" in text
        assert "DataDirName = 'YandexBusinessParser'" in text
        # установщик ставит метку, по которой paths уводит данные в AppData
        assert "'.installed'" in text or ".installed" in text
        # portable-метки не попадают в установленную копию
        assert ".portable" in text
        assert "Excludes:" in text
        # …а если пользователь сам включил portable у установленной копии,
        # удаление не должно молча снести его данные вместе с {app}.
        assert "Отменить удаление, чтобы сохранить данные?" in text
        assert "Abort;" in text

    def test_script_is_utf8_with_bom(self):
        """Кириллица в ярлыках и вопросах требует BOM.

        Inno Setup до 6.3 распознаёт UTF-8 только по BOM; без него название
        ярлыка и текст вопросов при удалении приезжают кракозябрами.
        """
        assert ISS.read_bytes()[:3] == b"\xef\xbb\xbf", "windows.iss без UTF-8 BOM"
        
    def test_fallback_version_matches_the_app(self):
        """Ручной iscc без /DMyAppVersion не должен выпустить старую версию."""
        from config import APP_VERSION
        text = ISS.read_text(encoding="utf-8")
        assert f'#define MyAppVersion "{APP_VERSION}"' in text
        assert f'/DMyAppVersion={APP_VERSION}' in text

    def test_release_builds_and_attaches_the_installer(self):
        text = WF.read_text(encoding="utf-8")
        assert "innosetup" in text.lower()
        assert "installer\\windows.iss" in text
        assert "YandexBusinessParser-windows-x64-setup.exe" in text
        # установщик должен уехать на релиз, а не остаться только артефактом
        assert "dist/YandexBusinessParser-windows-x64-setup.exe" in text
        # …и проверяться тем же скриптом, что архив: битый setup.exe иначе
        # всплывёт только у пользователя.
        assert "verify_release_assets.py --check-local $setup" in text

class TestDataDir:
    def _frozen(self, monkeypatch, exe: Path, appdata: Path):
        exe.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(paths, "is_frozen", lambda: True)
        monkeypatch.setattr(paths, "_is_macos", lambda: False)
        monkeypatch.setattr(paths, "_exe_dir", lambda: exe)
        monkeypatch.setenv("APPDATA", str(appdata))

    def test_installed_build_uses_appdata(self, monkeypatch, tmp_path):
        exe = tmp_path / "Programs" / "YandexBusinessParser"
        appdata = tmp_path / "Roaming"
        self._frozen(monkeypatch, exe, appdata)
        (exe / ".installed").write_text("installed", encoding="utf-8")
        assert paths.data_dir() == appdata / "YandexBusinessParser"

    def test_portable_marker_wins_over_installed(self, monkeypatch, tmp_path):
        exe = tmp_path / "Programs" / "YandexBusinessParser"
        appdata = tmp_path / "Roaming"
        self._frozen(monkeypatch, exe, appdata)
        (exe / ".installed").write_text("installed", encoding="utf-8")
        (exe / ".portable").write_text("portable", encoding="utf-8")
        assert paths.data_dir() == exe

    def test_zip_build_without_marker_stays_portable(self, monkeypatch, tmp_path):
        exe = tmp_path / "Downloads" / "YandexBusinessParser"
        appdata = tmp_path / "Roaming"
        self._frozen(monkeypatch, exe, appdata)
        assert paths.data_dir() == exe

    def test_explicit_data_dir_wins(self, monkeypatch, tmp_path):
        exe = tmp_path / "Programs" / "YandexBusinessParser"
        appdata = tmp_path / "Roaming"
        target = tmp_path / "custom-data"
        self._frozen(monkeypatch, exe, appdata)
        (exe / ".installed").write_text("installed", encoding="utf-8")
        monkeypatch.setenv("YP_DATA_DIR", str(target))
        assert paths.data_dir() == target

    def test_install_migrates_portable_data_once(self, monkeypatch, tmp_path):
        exe = tmp_path / "Programs" / "YandexBusinessParser"
        appdata = tmp_path / "Roaming"
        self._frozen(monkeypatch, exe, appdata)
        (exe / ".installed").write_text("installed", encoding="utf-8")
        (exe / ".env").write_text("VK_TOKEN=1", encoding="utf-8")
        (exe / "output").mkdir()
        (exe / "output" / "_reviewed.json").write_text("{}", encoding="utf-8")

        target = paths.data_dir()
        assert (target / ".env").read_text(encoding="utf-8") == "VK_TOKEN=1"
        assert (target / "output" / "_reviewed.json").exists()
        assert (target / ".migrated-from-portable").exists()
        # Повторный запуск не перезаписывает уже живущие данные.
        (target / ".env").write_text("VK_TOKEN=2", encoding="utf-8")
        assert paths.data_dir() == target
        assert (target / ".env").read_text(encoding="utf-8") == "VK_TOKEN=2"

    def test_migration_does_not_delete_the_portable_copy(self, monkeypatch, tmp_path):
        exe = tmp_path / "Programs" / "YandexBusinessParser"
        appdata = tmp_path / "Roaming"
        self._frozen(monkeypatch, exe, appdata)
        (exe / ".installed").write_text("installed", encoding="utf-8")
        (exe / ".env").write_text("VK_TOKEN=1", encoding="utf-8")
        paths.data_dir()
        assert (exe / ".env").exists()
