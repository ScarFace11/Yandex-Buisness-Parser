"""Ожидание двух зелёных сборок перед публикацией черновика.

Раньше это был bash с `sleep`, `case` и разбором строки через `${var%% *}` —
на Windows такой шаг не запускался. Теперь та же логика живёт здесь, а тесты
зовут функции напрямую.
"""
import os
import subprocess
import sys
import time

WORKFLOWS = ("build-exe.yml", "build-macos.yml")
# Успех — только success. Всё остальное либо ждём, либо останавливаемся.
FAILED_CONCLUSIONS = {"failure", "cancelled", "timed_out", "startup_failure",
                      "action_required"}
ATTEMPTS = 40
PAUSE = 30


def parse_run(line: str) -> tuple[str, str]:
    """Строка `gh run list --jq '.[0] | "status conclusion"'` → (status, conclusion)."""
    status, _, conclusion = (line or "").strip().partition(" ")
    return (status.strip() or "missing"), conclusion.strip()


def wait_for_builds(fetch, tag: str = "", workflows=WORKFLOWS,
                    attempts: int = ATTEMPTS, pause: float = PAUSE,
                    log=print, sleep=time.sleep) -> tuple[bool, str]:
    """`fetch(workflow)` отдаёт строку статуса; пусто — запуска ещё не было."""
    for attempt in range(1, attempts + 1):
        pending = []
        for workflow in workflows:
            status, conclusion = parse_run(fetch(workflow))
            log(f"{workflow}: status={status} conclusion={conclusion or '—'}")
            if conclusion == "success":
                continue
            if conclusion in FAILED_CONCLUSIONS:
                log(f"::error::{workflow} на {tag} завершился со статусом "
                    f"'{conclusion}' — релиз не публикуем.")
                return False, conclusion
            pending.append(workflow)
        if not pending:
            log(f"Обе сборки зелёные: {tag}")
            return True, "ok"
        log(f"Ждём ещё: {' '.join(pending)} (попытка {attempt}/{attempts})")
        if attempt < attempts:
            sleep(pause)
    log(f"::error::сборки для {tag} не позеленели за отведённое время — "
        "публикация отложена.")
    return False, "timeout"


def _gh_run_line(repo: str, workflow: str, tag: str) -> str:
    res = subprocess.run(
        ["gh", "run", "list", "--repo", repo, "--workflow", workflow,
         "--branch", tag, "--limit", "1", "--json", "status,conclusion",
         "--jq", '.[0] | "\\(.status) \\(.conclusion)"'],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        return "missing "
    return res.stdout.strip()


def _append(path_var: str, line: str) -> None:
    path = os.environ.get(path_var)
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    tag = os.environ.get("TAG", "")
    if "--tag" in argv:
        tag = argv[argv.index("--tag") + 1]
    repo = os.environ.get("REPO", "")
    attempts = int(os.environ.get("PWAIT_ATTEMPTS", str(ATTEMPTS)))
    pause = float(os.environ.get("PWAIT_SLEEP", str(PAUSE)))
    ok, _reason = wait_for_builds(
        lambda workflow: _gh_run_line(repo, workflow, tag),
        tag, attempts=attempts, pause=pause)
    if ok:
        _append("GITHUB_OUTPUT", "ok=true")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
