"""In-app self-update for the frozen Windows build."""
import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

from flask import Blueprint, jsonify, request

try:
    import paths
except Exception:
    paths = None

bp = Blueprint("update", __name__)

APP_DIR_NAME = "YandexBusinessParser"     # top-level folder inside the release zip
EXE_NAME = "YandexBusinessParser.exe"
ZIP_ASSET_NAME = "YandexBusinessParser-windows-x64.zip"
# Файлы релиза по системам.
MAC_ZIP_TMPL = "YandexBusinessParser-macos-{arch}.zip"
MAC_DMG_TMPL = "YandexBusinessParser-macos-{arch}.dmg"
STATE_FILE = "_update_state.json"         # progress for /update/status polling
ASSET_CACHE_TTL = 10 * 60                 # секунд: кэш проверки релиза по API
# Кэш минимально допустимой версии: она меняется раз в несколько релизов, а проверка идёт на каждом открытии окна.
MIN_VERSION_TTL = 60 * 60
EXIT_MARKER = "app.exit"                  # the app writes this right before exiting
LOG_FILE = "update.log"                   # updater.bat trace, for diagnostics

# popen kwargs that work the same on all supported Python versions
_DETACHED = {"creationflags": getattr(subprocess, "DETACHED_PROCESS", 0), "close_fds": True}


def _is_frozen() -> bool:
    return bool(paths and paths.is_frozen())


def _self_update_supported() -> bool:
    """Менять файлы на диске умеет только Windows-сборка (updater.bat + exe). macOS-версия — .app-бандл: подмена файлов запущенного бандла ломает подпись, а сам он может лежать в /Applications без права на запись."""
    import sys
    return sys.platform.startswith("win")


def _platform_refusal() -> dict:
    return {"ok": False,
            "error": "Авто-обновление доступно только в сборке для Windows. "
                     "Скачайте новую версию со страницы релизов."}


def _user_dir() -> Path:
    return Path(paths.user_dir()) if paths else Path.cwd()


def _app_root() -> Path:
    """Folder that contains the exe and _internal/ (works for onefile too)."""
    if paths and paths.is_frozen():
        return Path(sys_executable()).resolve().parent
    return Path(__file__).resolve().parent.parent


def sys_executable() -> str:
    import sys
    return sys.executable


def _work_dir() -> Path:
    d = _user_dir() / "_update"
    d.mkdir(exist_ok=True)
    return d


def _state() -> dict:
    f = _work_dir() / STATE_FILE
    if f.exists():
        try:
            return _json_load(f)
        except Exception:
            pass
    return {}


def _json_load(f: Path) -> dict:
    import json
    with open(f, encoding="utf-8") as fh:
        return json.load(fh)


def _save_state(**kw) -> None:
    import json
    data = _state()
    data.update(kw)
    with open(_work_dir() / STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _remote_meta() -> dict:
    """Latest release metadata from static/version.json on GitHub main."""
    import requests
    from routes.api import GITHUB_RAW_URL
    r = requests.get(GITHUB_RAW_URL, timeout=10,
                     headers={"User-Agent": "YandexParser-Updater/1.0"})
    r.raise_for_status()
    return r.json()


def _releases_page() -> str:
    """Human-facing release page (banner link when self-update is unavailable)."""
    try:
        from routes.api import GITHUB_REPO
    except Exception:
        return ""
    return f"https://github.com/{GITHUB_REPO}/releases/latest"


def _mac_arch() -> str:
    """arm64 у Apple Silicon, x64 у Intel (и всё неопознанное — x64)."""
    try:
        import platform as _platform
        machine = (_platform.machine() or "").strip().lower()
    except Exception:
        machine = ""
    return "arm64" if machine in ("arm64", "aarch64") else "x64"


def _release_asset_name(install: bool = False) -> str:
    """Имя файла релиза для ТЕКУЩЕЙ системы. `install=True` — формат для ручной установки: на macOS это .dmg (образ, который монтируется и перетаскивается в «Программы»), на Windows — тот же zip с exe (его ставит и внутренний обновлятор)."""
    import sys
    if sys.platform == "darwin":
        tmpl = MAC_DMG_TMPL if install else MAC_ZIP_TMPL
        return tmpl.format(arch=_mac_arch())
    return ZIP_ASSET_NAME


def _versioned_asset_url(version: str, url: str, asset: str = ZIP_ASSET_NAME) -> str:
    """`url` if it is pinned to v<version> **and** points at `asset`, else ""."""
    version = str(version or "").strip()
    url = str(url or "").strip()
    if not version or not url:
        return ""
    if f"/releases/download/v{version}/" not in url:
        return ""
    return url if url.rstrip("/").endswith("/" + str(asset or "")) else ""


def _release_asset_url(version: str, asset: str = ZIP_ASSET_NAME,
                       use_cache: bool = True) -> str:
    """browser_download_url of the requested asset of EXACTLY the v<version> release. `/releases/tags/v<version>` is used instead of `/releases/latest`: it answers 404 while the release is a draft or was deleted, and that is precisely the case we must not treat as an available update."""
    version = str(version or "").strip()
    asset = str(asset or ZIP_ASSET_NAME).strip()
    if not version:
        return ""
    cache = _state().get("asset") or {}
    if (use_cache and cache.get("version") == version
            and cache.get("asset") == asset):
        if time.time() - float(cache.get("at") or 0) < ASSET_CACHE_TTL:
            return str(cache.get("url") or "")
    url = ""
    try:
        import requests
        from routes.api import GITHUB_REPO
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/v{version}",
            timeout=10,
            headers={"User-Agent": "YandexParser-Updater/1.0",
                     "Accept": "application/vnd.github+json"},
        )
        if r.status_code == 200:
            data = r.json() or {}
            if not data.get("draft"):
                for found in data.get("assets", []):
                    if found.get("name") == asset:
                        url = found.get("browser_download_url", "")
                        break
    except Exception:
        pass
    _save_state(asset={"version": version, "asset": asset, "url": url,
                       "at": time.time()})
    return url


def _download_target(latest: str, stamped_url: str = "",
                     asset: str = ZIP_ASSET_NAME) -> tuple:
    """(url, reason) — where the advertised version can really be downloaded. 1. the URL stamped into version.json, when it is pinned to v<latest> (no network call needed — the normal case); 2. otherwise the asset of the exact v<latest> release through the API; 3. otherwise an empty url and a message explaining that the release is not published yet, so the caller can tell the truth instead of offering an update that would silently no-op."""
    version = str(latest or "").strip()
    asset = str(asset or ZIP_ASSET_NAME).strip()
    if not version:
        return "", "Неизвестна версия обновления — повторите проверку позже."
    pinned = _versioned_asset_url(version, stamped_url, asset)
    if pinned:
        return pinned, ""
    resolved = _release_asset_url(version, asset)
    if resolved:
        return resolved, ""
    return "", (f"Релиз v{version} ещё не опубликован на GitHub. Обновление "
                 "появится здесь сразу после публикации релиза.")


def _ver_tuple(v: str):
    return tuple(int(x) for x in str(v).split(".") if x.isdigit())


def _versions_below(current: str, minimum: str) -> bool:
    """Версия `current` старше `minimum` (учитывая разную длину чисел)."""
    a = _ver_tuple(current or "0")
    b = _ver_tuple(minimum or "0")
    if not b:
        return False                       # порог не задан — не блокируем
    a = a + (0,) * (len(b) - len(a))
    b = b + (0,) * (len(a) - len(b))
    return a < b


def _is_local_build() -> bool:
    """Локальная сборка/источник: порог минимальной версии не применяется."""
    try:
        from config import skips_min_version
        return bool(skips_min_version())
    except Exception:
        return False


def minimum_state() -> dict:
    """Состояние порога минимальной версии — «ниже не работаем»."""
    from config import APP_VERSION
    out = {"current": APP_VERSION, "minimum": "", "blocked": False,
           "download_url": _releases_page(),
           "auto_apply": _is_frozen() and _self_update_supported(),
           "bypass": False, "notice": ""}
    if _is_local_build():
        # Своя сборка: порог не мешает — так автор запускает и старые версии.
        out["bypass"] = True
        return out

    cache = _state().get("min_version") or {}
    cached = cache.get("payload") or {}
    fresh = (cache and time.time() - float(cache.get("at") or 0) < MIN_VERSION_TTL)
    if not (fresh and cached):
        try:
            meta = _remote_meta()
        except Exception:
            # Нет сети/репозиторий недоступен: работаем, но честно говорим, что проверить не смогли.
            cached = dict(cached) if cached else {}
            out["notice"] = ("Не удалось проверить минимальную версию "
                             "(GitHub недоступен) — обновление проверьте вручную.")
            out["minimum"] = str(cached.get("min_version") or "")
            out["blocked"] = _versions_below(APP_VERSION, out["minimum"])
            return out
        cached = {"min_version": str(meta.get("min_version") or ""),
                  "version": str(meta.get("version") or "")}
        _save_state(min_version={"payload": cached, "at": time.time()})

    out["minimum"] = str(cached.get("min_version") or "")
    latest = str(cached.get("version") or "")
    out["latest"] = latest
    out["blocked"] = _versions_below(APP_VERSION, out["minimum"])
    if out["blocked"]:
        # Цель обновления — не «последняя объявленная», а ГАРАНТИРОВАННО рабочая:
        target = latest if not _versions_below(latest, out["minimum"]) else out["minimum"]
        out["target"] = target
        out["notice"] = ("Эта версия больше не поддерживается: обновитесь до "
                         f"v{target} или новее.")
    return out


@bp.route("/version/minimum")
def version_minimum():
    """Минимально допустимая версия: окно «нужно обновить»."""
    return jsonify(minimum_state())

def _last_update_result() -> dict:
    """Результат последней установки, который помощник пишет вне приложения.

    Сбой после выхода приложения иначе выглядел бы как «нажал Обновить,
    окно закрылось, версия та же»: помощник вернул старую версию на место,
    но сказать об этом уже некому. Показываем причину при следующем старте.
    """
    from config import APP_VERSION
    path = _work_dir() / "update_result.json"
    if not path.exists():
        return {}
    try:
        data = _json_load(path)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    # Успешная установка той версии, которая сейчас запущена, — не новость.
    if data.get("ok") and str(data.get("version") or "") == APP_VERSION:
        return {}
    data["log"] = str(_work_dir() / LOG_FILE)
    return data


@bp.route("/update/status")
def update_status():
    from config import APP_VERSION
    import sys
    try:
        import update_notes
        texts = update_notes.texts()
    except Exception:
        texts = {}
    out = {
        "texts": texts,
        "last_update": _last_update_result(),
        "frozen": _is_frozen(),
        "current": APP_VERSION,
        "latest": None,
        "newer": False,
        "changelog": "",
        "download_url": "",
        # Какой файл релиза нужен ИМЕННО этой системе: windows-zip или macos-<arch>.dmg.
        "asset_name": _release_asset_name(install=True),
        # false → в баннере нет кнопки «Обновить сейчас» (macOS/исходники).
        "auto_apply": _is_frozen() and _self_update_supported(),
        "platform": sys.platform,
        "state": _state(),
    }
    # Из исходников за версией не ходим: обновление предлагается только сборке.
    if not _is_frozen():
        return jsonify(out)
    try:
        meta = _remote_meta()
        out["latest"] = meta.get("version", "")
        out["changelog"] = meta.get("changelog", "")
        stamped = meta.get("download_url", "")
        out["download_url"] = _releases_page()
        out["newer"] = _ver_tuple(out["latest"] or "0") > _ver_tuple(APP_VERSION)
        if out["newer"]:
            # Версия, до которой предлагается обновиться, и файл под эту систему — баннер показывает и то, и другое.
            out["target_version"] = out["latest"]
            url, why = _download_target(out["latest"], stamped, out["asset_name"])
            if url:
                out["download_url"] = url
            else:
                # Advertised but not installable (release still a draft, was deleted, ...).
                out["newer"] = False
                out["notice"] = why
        # Сборка ниже порога не должна предлагать установку версии, которая тоже ниже порога (на main объявлена предыдущая, пока свежий релиз — черновик).
        blocked_state = minimum_state()
        if blocked_state.get("blocked"):
            out["newer"] = False
            out["blocked"] = True
            out["minimum"] = blocked_state.get("minimum", "")
            out["notice"] = blocked_state.get("notice", "")
            out["download_url"] = blocked_state.get("download_url", "")

        # Remember the advertised version for /update/apply: the bat is built later, and the zip must be verified against the SAME advertised version even if GitHub is unreachable by then.
        _save_state(latest=out["latest"], download_url=out["download_url"],
                    stamped_url=stamped)
    except Exception as exc:
        out["error"] = str(exc)
    return jsonify(out)


def _history_row(raw: dict) -> dict:
    """Запись истории к одной форме: version/date/title/summary/items."""
    if not isinstance(raw, dict):
        return {}
    items = []
    for item in raw.get("items") or []:
        if isinstance(item, str):
            items.append({"title": "", "text": item})
            continue
        if not isinstance(item, dict):
            continue
        items.append({"title": str(item.get("title") or ""),
                      "text": str(item.get("text") or "")})
    return {
        "version": str(raw.get("version") or ""),
        "date": str(raw.get("date") or ""),
        "title": str(raw.get("title") or ""),
        "summary": str(raw.get("summary") or raw.get("changelog") or ""),
        "items": [i for i in items if i["text"]],
    }


@bp.route("/update/changelog")
def update_changelog():
    """История версий для окна «Что нового»: сеть плюс заметки самой сборки."""
    from config import APP_VERSION
    import update_notes

    bundled = {}
    try:
        import json as _json
        path = (paths.resource_dir() if paths else Path(__file__).resolve().parent.parent) / "static" / "version.json"
        bundled = _json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        bundled = {}
    if not isinstance(bundled, dict):
        bundled = {}

    try:
        meta = _remote_meta()
        if not isinstance(meta, dict):
            raise ValueError("version.json: ожидался объект")
    except Exception:
        # Офлайн: история из version.json самой сборки — окно всё равно открывается.
        meta = dict(bundled)
        meta["offline"] = True

    # Собираем все известные версии: старые — из сети и из version.json,
    # заметки сборки главнее — в них краткое описание и полный текст.
    rows: dict[str, dict] = {}
    for source in (bundled.get("history") or [], meta.get("history") or []):
        for raw in source:
            row = _history_row(raw)
            if row["version"]:
                rows[row["version"]] = row
    top = _history_row(meta)
    if top["version"]:
        rows.setdefault(top["version"], top)
    for note in update_notes.releases():
        if note.get("version"):
            rows[note["version"]] = note

    history = sorted(rows.values(), key=lambda r: _ver_tuple(r["version"]),
                     reverse=True)[:update_notes.HISTORY_LIMIT]
    newest = history[0] if history else _history_row({"version": APP_VERSION})
    out = dict(meta)
    out["version"] = newest.get("version") or APP_VERSION
    out["changelog"] = newest.get("summary", "")
    out["history"] = history
    out["texts"] = update_notes.texts()
    out["current"] = APP_VERSION
    return jsonify(out)


@bp.route("/update/download", methods=["POST"])
def update_download():
    """Скачать файл обновления: zip для Windows, dmg для macOS."""
    if not _is_frozen():
        return jsonify({"ok": False, "error": "Доступно только в собранном приложении"}), 400
    import sys as _sys
    mac = _sys.platform == "darwin"
    if not mac and not _self_update_supported():
        return jsonify(_platform_refusal()), 400

    state = _state()
    explicit = (request.get_json(silent=True) or {}).get("url")
    url = explicit or ""
    if not url:
        # NEVER fall back to the stamped `releases/latest/download/...` alias:
        latest = str(state.get("latest") or "")
        stamped = str(state.get("stamped_url") or "")
        if not latest:
            try:
                meta = _remote_meta()
                latest = meta.get("version", "")
                stamped = meta.get("download_url", "")
            except Exception:
                pass
        url, why = _download_target(latest, stamped)
        if not url:
            return jsonify({"ok": False, "error": why or "Не найден адрес обновления"}), 400
    _save_state(download_url=url)

    import requests
    try:
        r = requests.get(url, stream=True, timeout=(10, 300),
                         headers={"User-Agent": "YandexParser-Updater/1.0"})
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        target = _work_dir() / ("update.dmg" if mac else "update.zip")
        done = 0
        with open(target, "wb") as f:
            for chunk in r.iter_content(chunk_size=256 * 1024):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
        if total and done != total:
            return jsonify({"ok": False,
                            "error": f"Архив скачан неполностью ({done} из {total} байт)"}), 502
        _save_state(download={"done": done, "total": total,
                              "file": str(target), "url": url})
        return jsonify({"ok": True, "bytes": done, "total": total, "file": str(target)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


@bp.route("/update/apply", methods=["POST"])
def update_apply():
    """Extract the downloaded zip, verify it, schedule the swap, restart."""
    if not _is_frozen():
        return jsonify({"ok": False, "error": "Доступно только в собранном приложении"}), 400

    # macOS: подменять запущенный .app нельзя — скачанный .dmg открывается,
    # пользователь перетаскивает приложение в «Программы» сам.
    import sys as _sys
    if _sys.platform == "darwin":
        st = _state()
        dmg = Path(st.get("download", {}).get("file") or (_work_dir() / "update.dmg"))
        if not dmg.exists():
            return jsonify({"ok": False, "error": "Обновление ещё не скачано"}), 400
        try:
            subprocess.Popen(["open", str(dmg)])
        except OSError as exc:
            return jsonify({"ok": False,
                            "error": f"Не удалось открыть образ: {exc}"}), 500
        return jsonify({"ok": True, "manual": True,
                        "message": "Образ открыт — перетащите приложение в «Программы»."})

    if not _self_update_supported():
        return jsonify(_platform_refusal()), 400

    st = _state()
    zip_path = Path(st.get("download", {}).get("file") or (_work_dir() / "update.zip"))
    if not zip_path.exists():
        return jsonify({"ok": False, "error": "Обновление ещё не скачано"}), 400

    work = _work_dir()
    extract = work / "extracted"
    if extract.exists():
        shutil.rmtree(extract, ignore_errors=True)
        # exist_ok: помощник прошлого обновления ещё мог держать свои файлы в
    # распакованной папке, и rmtree не удалил её целиком.
    extract.mkdir(parents=True, exist_ok=True)

    # 1. Extract
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Архив повреждён: {exc}"}), 400

    # 2. Locate the new app folder (zip may or may not have a top-level dir)
    src = extract
    if not (src / EXE_NAME).exists():
        inner = src / APP_DIR_NAME
        if (inner / EXE_NAME).exists():
            src = inner
        else:
            return jsonify({"ok": False, "error": "В архиве нет " + EXE_NAME}), 400
    if not (src / "_internal").exists():
        return jsonify({"ok": False, "error": "В архиве нет _internal — повреждённая сборка"}), 400

    # 3. Verify the version INSIDE the zip against the advertised one.
    advertised = str(st.get("latest") or "").strip()
    zip_version = ""
    for cand in (src / "_internal" / "static" / "version.json",
                 src / "static" / "version.json"):
        if cand.exists():
            try:
                zip_version = str(_json_load(cand).get("version", "")).strip()
            except Exception:
                zip_version = ""
            break
    if advertised and zip_version and _ver_tuple(zip_version) < _ver_tuple(advertised):
        try:
            zip_path.unlink()
        except OSError:
            pass
        _save_state(error=f"В архиве v{zip_version}, ожидалась v{advertised}")
        return jsonify({
            "ok": False,
            "error": f"В архиве версия v{zip_version}, а ожидалась v{advertised}: "
                     "релиз ещё не опубликован. Скачайте новую версию вручную "
                     "со страницы релизов (кнопка GitHub ↗)."}), 409
    new_version = zip_version or advertised

    app_root = _app_root()

    # 4. Задание для помощника: его запускает НОВАЯ сборка уже после выхода
    # приложения. Пути передаются JSON-файлом, а не через cmd.exe: кириллица
    # и пробелы в пути не теряются.
    work = _work_dir()
    backup = work / "_backup"
    marker = work / EXIT_MARKER
    log = work / LOG_FILE
    job = work / "update_job.json"
    try:
        import json as _json
        job.write_text(_json.dumps({
            "app_root": str(app_root),
            "src": str(src),
            "backup": str(backup),
            "marker": str(marker),
            "log": str(log),
            "zip_path": str(zip_path),
            "version": new_version,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        return jsonify({"ok": False,
                        "error": f"Не удалось записать задание обновления: {exc}"}), 500

    _save_state(applied=True, new_version=new_version,
                previous_version=st.get("current", ""), error="",
                job=str(job))

    # 5. Запускаем помощника из распакованной сборки и сигналим выход.
    if marker.exists():
        try:
            marker.unlink()
        except OSError:
            pass
    helper = src / EXE_NAME
    try:
        subprocess.Popen([str(helper), "--apply-update", str(job)],
                         cwd=str(src), **_DETACHED)
    except OSError as exc:
        return jsonify({"ok": False,
                        "error": f"Не удалось запустить помощник обновления: {exc}"}), 500
    try:
        marker.write_text("exit", encoding="ascii")
    except OSError:
        pass

    # 6. Дать ответу уйти и жёстко завершиться: запущенный exe держит сам
    # себя, а помощник меняет файлы только после выхода процесса (маркер и
    # повторы помощника закрывают этот промежуток).
    def _bye():
        import time as _t
        _t.sleep(1.0)
        os._exit(0)

    import threading
    threading.Thread(target=_bye, daemon=True).start()
    return jsonify({"ok": True, "message": "Обновление установлено — приложение перезапускается…",
                    "new_version": new_version})
