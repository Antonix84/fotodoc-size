"""Проверка установленного скрипта — того, что запускает горячая клавиша.

Скрипт лежит в папке Photoshop, а программа — в папке проекта; проверка
именно этого расклада: обмен через папку работы и запуск Python оттуда.

    python tools\\e2e_installed.py [номер_пары]

Окно выбора размера здесь не появляется: размер передаётся ключом auto_size
в passport_paths2.txt. Само окно проверяет tools\\test_dialog.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import win32com.client
from pp import installer

from pp import bridge, config

INSTALLED = Path(r"F:\PROGS\Photo\Adobe Photoshop 2025\Presets\Scripts")
JSX_NAME = "passport-photo2.jsx"


def main() -> int:
    number = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    size_id = sys.argv[2] if len(sys.argv) > 2 else config.BASE_PRESET_ID
    jsx = INSTALLED / JSX_NAME
    if not jsx.is_file():
        print(f"Установленный скрипт не найден: {jsx}\n"
              "Запустите:  python tools\\install_jsx.py")
        return 1

    source = config.samples_dir() / f"source{number}.jpg"
    if not source.exists():
        print(f"Нет файла {source}")
        return 1

    # Настройки читает установленный скрипт — правим те же строки.
    config_path = jsx.parent / installer.PATHS_NAME
    settings = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    lines = [line for line in settings.splitlines()
             if not line.startswith("auto_size=")]
    lines.append(f"auto_size={size_id}")
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

# Папка обмена — та, что прописана в самом файле настроек: установленный
    # скрипт работает с exe, а не с исходниками, и папка у него своя.
    installed = installer.installed_paths(jsx.parent)
    work = Path(installed["work"]) if installed.get("work") else bridge.work_dir()

    bridge.cleanup()
    for stale in (work / bridge.JOB_NAME, work / bridge.TRANSFORM_NAME,
                  work / bridge.DONE_NAME, work / bridge.SOURCE_NAME):
        stale.unlink(missing_ok=True)
    app = win32com.client.GetActiveObject("Photoshop.Application")
    for doc in list(app.Documents):
        doc.Close(2)
    app.Open(str(source))
    print("открыт документ:", app.ActiveDocument.Name, flush=True)
    print("запускаю:", jsx, flush=True)

    script = "$.evalFile(new File(\"" + str(jsx).replace("\\", "/") + "\")); 'ок'"
    try:
        app.DoJavaScript(script)
    except Exception as exc:  # noqa: BLE001
        info = getattr(exc, "excepinfo", None)
        print("ошибка:", str(info[2] if info and info[2] else exc)[:400], flush=True)
        return 1

    done = work / bridge.DONE_NAME
    if not done.exists():
        print("Скрипт не оставил done.txt", flush=True)
        logs = sorted(work.glob("program-*.log"),
                      key=lambda p: p.stat().st_mtime)
        if logs:
            print(logs[-1].read_text(encoding="utf-8", errors="replace")[-1500:],
                  flush=True)
        return 1

    answer = bridge._read(done)
    print("done:", answer, flush=True)
    result = Path(answer.get("result", ""))
    if result.is_file():
        print("файл:", result, result.stat().st_size, "байт")
    done.unlink(missing_ok=True)   # этот файл читает ещё и программа
    return 0 if answer.get("ok") == "1" else 1


if __name__ == "__main__":
    raise SystemExit(main())

