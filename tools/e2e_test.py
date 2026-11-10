"""Запуск всей цепочки в настоящем Photoshop — как это сделает горячая клавиша.

Открывает source*.jpg, выполняет passport-photo.jsx внутри Photoshop (тем же
путём, каким его запускает действие «выполнить сценарий»), и ждёт результата.
Размер задаётся переменной PASSPORT_AUTO_SIZE, поэтому окно выбора не нужно.

ВНИМАНИЕ: скрипт закрывает все открытые документы, не сохраняя их.

    python tools\\e2e_test.py [номер_пары] [размер]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import win32com.client

from pp import bridge, config, installer

JSX = config.APP_DIR / "passport-photo.jsx"


def main() -> int:
    number = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    size_id = sys.argv[2] if len(sys.argv) > 2 else config.BASE_PRESET_ID
    source = config.samples_dir() / f"source{number}.jpg"
    if not source.exists():
        print(f"Нет файла {source}")
        return 1

    bridge.cleanup()

    app = win32com.client.GetActiveObject("Photoshop.Application")
    for doc in list(app.Documents):
        doc.Close(2)
    app.Open(str(source))
    print("открыт документ:", app.ActiveDocument.Name, flush=True)

    script = (
        "$.evalFile(new File(\"" + str(JSX).replace("\\", "\\\\") + "\")); 'запущено'"
    )

    # Размер передаём через passport_paths.txt: переменные окружения сюда не
    # доедут, ведь Python запускает сам Photoshop.
    (config.APP_DIR / "passport_paths.txt").write_text(
        installer.paths_text(bridge.work_dir()) + f"auto_size={size_id}\n",
        encoding="utf-8")

    # Скрипт сам запустит Python и дождётся результата. Отдельного ожидания не
    # нужно: в тихом режиме DoJavaScript возвращается, когда скрипт закончил.
    done = bridge.work_dir() / bridge.DONE_NAME
    try:
        print("запускаю скрипт в Photoshop…", flush=True)
        app.DoJavaScript(script)
    except Exception as exc:  # noqa: BLE001
        info = getattr(exc, "excepinfo", None)
        print("Photoshop не смог выполнить скрипт:",
              str(info[2] if info and info[2] else exc)[:500], flush=True)
        return 1

    if not done.exists():
        log = bridge.work_dir() / "program.log"
        if log.is_file():
            print("--- что вывела программа ---", flush=True)
            print(log.read_text(encoding="utf-8", errors="replace")[-3000:],
                  flush=True)
        print("Скрипт отработал, но не оставил done.txt", flush=True)
        return 1

    answer = bridge._read(done)
    print("done получен:", answer, flush=True)
    if answer.get("ok") != "1":
        bridge.cleanup()
        return 1

    result = Path(answer.get("result", ""))
    if result.is_file():
        print("файл:", result, result.stat().st_size, "байт")
    time.sleep(1)
    bridge.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
