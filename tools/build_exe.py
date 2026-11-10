"""Сборка портативной программы.

    python tools\\build_exe.py

Делает папку dist\\passport: passport.exe, встроенные модели, шаблон и скрипт
для Photoshop. Python на чужом компьютере не нужен — внутри exe всё своё.

Что и куда кладётся:
    models\\*.onnx, 3,7x4,7.psd, passport-photo.jsx — внутрь exe (папка _internal),
    passport.ini — рядом с exe, его создаёт сама программа при первом запуске.

После сборки рядом с exe появляется только то, что можно редактировать руками.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
NAME = "passport"
ENTRY = PROJECT / "passport.py"
VERSION_INFO = PROJECT / "packaging" / "version_info.txt"

# onnxruntime тянет за собой провайдеры, которые PyInstaller не всегда находит
# сам: собираем пакет целиком, иначе exe падает с «No such file: onnxruntime…».
COLLECT = ["onnxruntime", "numpy", "PIL", "tkinter"]

# PyInstaller разделяет источник и назначение данных двоеточием. На Windows
# путь с буквой диска выглядит двусмысленно, но разбирает он именно так.
DATA_SEP = ":"


def main() -> int:
    if not ENTRY.is_file():
        print(f"Нет {ENTRY}")
        return 1

    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", NAME,
        "--paths", str(PROJECT),
        "--distpath", str(PROJECT / "dist"),
        "--workpath", str(PROJECT / "build"),
        "--specpath", str(PROJECT / "build"),
        "--version-file", str(VERSION_INFO),
    ]
    for item in COLLECT:
        command += ["--collect-all", item]
    command += [f"--add-data={PROJECT / 'models'}{DATA_SEP}models",
                f"--add-data={PROJECT / '3,7x4,7.psd'}{DATA_SEP}templates",
                f"--add-data={PROJECT / 'passport-photo.jsx'}{DATA_SEP}."]
    command.append(str(ENTRY))

    print(" ".join(command))
    result = subprocess.run(command, cwd=str(PROJECT))
    if result.returncode != 0:
        return result.returncode

    folder = PROJECT / "dist" / NAME
    print()
    print(f"Готово: {folder}")
    size = sum(f.stat().st_size for f in folder.rglob('*') if f.is_file())
    print(f"Размер: {size / 1024 / 1024:.0f} МБ")
    print("Проверка на чужом компьютере: скопируйте всю папку и запустите "
          "passport.exe install.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
