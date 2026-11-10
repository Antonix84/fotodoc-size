"""Проверка всей цепочки без Photoshop.

Делает ровно то, что делает скрипт Photoshop: пишет job.txt, запускает
passport.py, читает transform.txt, применяет его к копии исходника средствами
Pillow и пишет done.txt. Так проверяется весь обмен файлами и вся математика,
а Photoshop не трогается.

Программа запускается без диалогов: PASSPORT_AUTO_SIZE задаёт размер,
PASSPORT_NO_REPORT=1 печатает отчёт в консоль.

    python tools\\simulate_photoshop.py [номер_пары] [размер]
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from pp import bridge, config

PROGRAM = config.self_command()
# Photoshop кладёт во временный PSD, а Pillow PSD писать не умеет. Здесь PNG:
# программе всё равно, лишь бы читалось.
SOURCE_PNG = "source.png"


def apply_transform(source: Path, target: Path, request: dict) -> dict:
    """Повторяет то, что Photoshop делает со слоем: поворот → масштаб → сдвиг.

    Отличие от наивного поворота: Photoshop увеличивает слой при повороте, а
    Pillow по умолчанию обрезает по углам. Поэтому expand=True, и центр
    слоя остаётся на месте — ровно как в Photoshop.
    """
    dx = float(request["tx"])
    dy = float(request["ty"])
    with Image.open(source) as im:
        im = im.convert("RGB")
        src_w, src_h = im.size
        im = im.rotate(-float(request["rotateDeg"]), resample=Image.BICUBIC,
                       expand=True)
        percent = float(request["scalePercent"]) / 100
        size = (max(1, round(im.width * percent)), max(1, round(im.height * percent)))
        im = im.resize(size, Image.LANCZOS)
        # Центр слоя должен оказаться там же, куда его сдвинул Photoshop:
        # центр исходного холста плюс сдвиг.
        left = round(src_w / 2 + dx - size[0] / 2)
        top = round(src_h / 2 + dy - size[1] / 2)
        canvas = Image.new("RGB", (int(request["docWidth"]),
                                   int(request["docHeight"])), "white")
        canvas.paste(im, (left, top))
        target.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(target, "JPEG", quality=95, subsampling=0)
        return {"left": float(left), "top": float(top),
                "right": float(left) + size[0],
                "bottom": float(top) + size[1]}


def main() -> int:
    number = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    preset_id = sys.argv[2] if len(sys.argv) > 2 else config.BASE_PRESET_ID
    source = config.samples_dir() / f"source{number}.jpg"
    if not source.exists():
        print(f"Нет файла {source}")
        return 1

    bridge.cleanup()
    work = bridge.work_dir()
    work.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as im:
        im.convert("RGB").save(work / SOURCE_PNG, "PNG")

    out_dir = config.samples_dir() / "_проверка"
    bridge._write(work / bridge.JOB_NAME, {
        "source": source.name,
        "temp": str(work / SOURCE_PNG),
        "work": str(work),
        "sourcePath": str(out_dir / source.name),
    })
    print("job.txt записан, запускаю программу…", flush=True)

    env = dict(os.environ,
               PASSPORT_AUTO_SIZE=preset_id,
               PASSPORT_NO_REPORT="1")
    process = subprocess.Popen(list(PROGRAM), env=env)

    transform_path = work / bridge.TRANSFORM_NAME
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline and not transform_path.exists():
        time.sleep(0.2)
    if not transform_path.exists():
        print("Программа не ответила transform.txt")
        process.kill()
        return 1

    request = bridge._read(transform_path)
    if request.get("cancel"):
        print("Пользователь отменил — так и должно быть")
        process.wait(timeout=30)
        bridge.cleanup()
        return 0

    print("transform получен:", request, flush=True)
    result = Path(request["result"])
    bounds = apply_transform(work / SOURCE_PNG, result, request)

    done = {"ok": "1", "result": str(result),
            "docWidth": request["docWidth"], "docHeight": request["docHeight"]}
    done.update({k: str(round(v, 1)) for k, v in bounds.items()})
    bridge._write(work / bridge.DONE_NAME, done)
    print("done.txt записан, жду отчёт программы…", flush=True)

    code = process.wait(timeout=300)
    print("программа завершилась с кодом", code, flush=True)
    print("файл:", result, "размер:", result.stat().st_size, "байт")
    bridge.cleanup()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
