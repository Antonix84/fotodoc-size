"""Упаковка релизного архива.

    python tools\\package_release.py 2.0.0

Берёт готовую сборку dist\\passport, добавляет install.cmd, settings.cmd,
README.txt и лицензии, складывает всё в release\\fotodoc-size-2.0.0-win64.zip
и пишет рядом SHA256SUMS.txt.

Рабочие файлы (passport_work, журналы, ярлыки) в архив не попадают: это следы
запуска на машине сборки, а не часть поставки.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DIST = PROJECT / "dist" / "passport"
RELEASE = PROJECT / "release"
NAME = "fotodoc-size"

# Что положить рядом с exe, поверх содержимого dist.
EXTRA = [
    (PROJECT / "passport.ini", "passport.ini"),
    (PROJECT / "packaging" / "install.cmd", "install.cmd"),
    (PROJECT / "packaging" / "settings.cmd", "settings.cmd"),
    (PROJECT / "packaging" / "README.txt", "README.txt"),
    (PROJECT / "LICENSE", "LICENSE.txt"),
    (PROJECT / "THIRD-PARTY-NOTICES.md", "THIRD-PARTY-NOTICES.md"),
]

# Следы запуска программы на машине сборки.
SKIP_DIRS = {"passport_work", "__pycache__"}
SKIP_SUFFIXES = {".lnk", ".log"}


def iter_build_files(root: Path):
    """Файлы сборки в устойчивом порядке, без рабочих папок и журналов."""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        yield path, rel


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    version = sys.argv[1] if len(sys.argv) > 1 else "2.0.0"
    if not DIST.is_dir():
        print(f"Нет сборки {DIST}. Сначала: python tools\\build_exe.py")
        return 1
    for source, _name in EXTRA:
        if not source.is_file():
            print(f"Нет файла {source}")
            return 1

    RELEASE.mkdir(exist_ok=True)
    folder = f"{NAME}-{version}"
    archive = RELEASE / f"{folder}-win64.zip"

    temp = archive.with_suffix(".zip.tmp")
    if temp.exists():
        temp.unlink()

    print(f"Упаковка {archive.name}…")
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as bundle:
        for path, rel in iter_build_files(DIST):
            bundle.write(path, f"{folder}/{rel.as_posix()}")
        for source, name in EXTRA:
            bundle.write(source, f"{folder}/{name}")

    temp.replace(archive)

    checksum = sha256(archive)
    sums = RELEASE / "SHA256SUMS.txt"
    sums.write_text(f"{checksum}  {archive.name}\n", encoding="utf-8")

    size = archive.stat().st_size / 1024 / 1024
    print(f"Готово: {archive}")
    print(f"Размер: {size:.0f} МБ")
    print(f"SHA-256: {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
