"""Обмен файлами между Python и скриптом Photoshop.

Photoshop запускает нас через bat-файл и уходит в ожидание: ждать он может
только опрашивая файл. Поэтому сценарий такой:

    job.txt        Photoshop → Python: какой документ и что выгрузил
    transform.txt  Python → Photoshop: поворот, масштаб, сдвиг, куда сохранить
    done.txt       Photoshop → Python: готово, вот путь и границы слоя

Формат везде одинаковый — строки «ключ=значение». Так не нужен JSON: в
ExtendScript его нет, а пробелы и обратные слэши в путях остаются целыми.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import config

JOB_NAME = "job.txt"
TRANSFORM_NAME = "transform.txt"
DONE_NAME = "done.txt"
SOURCE_NAME = "source.psd"

POLL_INTERVAL = 0.25
WAIT_TIMEOUT = 600.0


class BridgeError(RuntimeError):
    """Скрипт Photoshop не отдал результат."""


def work_dir() -> Path:
    """Папка обмена с Photoshop. Путь задан в ini, иначе — рядом с программой."""
    return config.work_dir()


def _read(path: Path) -> dict:
    params: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        key, sep, value = line.partition("=")
        if sep and key:
            params[key.strip()] = value.strip()
    return params


def _write(path: Path, params: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={str(value).replace(chr(13), ' ').replace(chr(10), ' ')}"
             for key, value in params.items() if value not in (None, "")]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def wait_for(path: Path, timeout: float = WAIT_TIMEOUT,
             fresh_after: float | None = None) -> Path:
    """Ждёт появления файла. fresh_after — ждать и обновления: на случай,
    если файл остался от прошлого запуска."""
    deadline = time.monotonic() + timeout
    started = time.monotonic()
    while time.monotonic() < deadline:
        if path.exists():
            if fresh_after is None:
                return path
            age = time.time() - path.stat().st_mtime
            if age < fresh_after or time.monotonic() - started > 3.0:
                return path
        time.sleep(POLL_INTERVAL)
    raise BridgeError(
        f"Photoshop не создал файл {path.name} за {timeout:.0f} с. "
        "Проверьте, что скрипт отработал без ошибок в Photoshop.")


def read_job(timeout: float = WAIT_TIMEOUT) -> dict:
    """Читает задание от Photoshop."""
    path = wait_for(work_dir() / JOB_NAME, timeout)
    job = _read(path)
    if not job.get("source") or not job.get("temp"):
        raise BridgeError(f"Задание от Photoshop повреждено: {job}")
    return job


def read_last_log() -> str:
    """Текст последнего лога программы — показывается, если всё сломалось."""
    logs = sorted(work_dir().glob("program-*.log"), key=lambda p: p.stat().st_mtime)
    if not logs:
        return ""
    try:
        return logs[-1].read_text(encoding="utf-8", errors="replace")[-1500:]
    except OSError:
        return ""


def write_transform(params: dict) -> None:
    """Отдаёт Photoshop числа трансформации."""
    _write(work_dir() / TRANSFORM_NAME, params)


def cancel() -> None:
    """Пользователь закрыл окно выбора размера."""
    _write(work_dir() / TRANSFORM_NAME, {"cancel": "1"})


def wait_done(timeout: float = WAIT_TIMEOUT) -> dict:
    """Ждёт результата от Photoshop."""
    path = wait_for(work_dir() / DONE_NAME, timeout)
    done = _read(path)
    if done.get("ok") != "1":
        detail = done.get("error", "причина неизвестна")
        if done.get("line"):
            detail += f" (строка {done['line']})"
        raise BridgeError(f"Photoshop не смог собрать фотографию: {detail}")
    return done


def cleanup() -> None:
    """Убирает рабочие файлы. Их удаляет тот, кто прочитал последним."""
    for name in (JOB_NAME, TRANSFORM_NAME, DONE_NAME, SOURCE_NAME):
        try:
            (work_dir() / name).unlink()
        except OSError:
            pass


def clear_logs() -> None:
    """Оставляет только последний лог запуска — иначе они копятся месяцами."""
    logs = sorted(work_dir().glob("program-*.log"),
                  key=lambda p: p.stat().st_mtime)
    for old in logs[:-1]:
        try:
            old.unlink()
        except OSError:
            pass
