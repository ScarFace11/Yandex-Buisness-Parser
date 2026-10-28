"""Единый источник текста стилей для тестов.

Стили разбиты на упорядоченные части (static/css/00-…, 01-…). Тесты,
которые ищут правило по тексту, читают склейку в порядке каскада — так
же, как её подключает templates/index.html. Порядок задан именами:
две цифры в начале, поэтому sorted() совпадает с порядком ссылок.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS_DIR = ROOT / "static" / "css"


def css_files(root: Path = ROOT) -> list[Path]:
    """Части стилей по порядку каскада (без README и прочего)."""
    return sorted((root / "static" / "css").glob("*.css"))


def read_css(root: Path = ROOT) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in css_files(root))
