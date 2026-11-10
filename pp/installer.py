"""Установка скрипта в Photoshop.

Работает и из исходников, и из собранного exe — python не нужен:

    passport.exe install

Скрипт кладёт passport-photo2.jsx в папку Presets\\Scripts того Photoshop, который
найден, а рядом пишет passport_paths2.txt: чем запускать программу, где папка
обмена и какой размер брать без вопросов.

Поиск Photoshop идёт тремя способами, потому что год в имени папки меняется, а
версия одна и та же: путь из ini, реестр (где Photoshop сам себя записал) и
известные места. Папка скриптов берётся и системная (C:\\Program Files\\Adobe…,
нужны права администратора), и пользовательская (%APPDATA%\\Adobe… — права не
нужны, Photoshop видит обе).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import config

# Файл в проекте называется passport-photo.jsx, а в Photoshop кладётся под своим
# именем: так скрипт прежней версии остаётся рабочим рядом с новым.
SOURCE_JSX_NAME = "passport-photo.jsx"
JSX_NAME = "passport-photo2.jsx"
PATHS_NAME = "passport_paths2.txt"

# Куда смотреть, если не нашлось ни в реестре, ни в ini.
COMMON_ROOTS = [
    Path(r"C:\Program Files\Adobe"),
    Path(r"C:\Program Files (x86)\Adobe"),
    Path(r"F:\PROGS\Photo"),
    Path(r"D:\PROGS\Photo"),
    Path(r"D:\PROGS\Windows\Photo"),
]


def jsx_source() -> Path | None:
    """Откуда взять .jsx: путь из ini, рядом с программой, внутри exe."""
    raw = config.get("paths", "jsx_source")
    candidates = [Path(raw)] if raw else []
    candidates += [config.APP_DIR / SOURCE_JSX_NAME,
                   config.BUNDLE_DIR / SOURCE_JSX_NAME]
    for path in candidates:
        if path.is_file():
            return path
    return None


# ── Где живёт Photoshop ──────────────────────────────────────────────────────


def photoshop_from_registry() -> Path | None:
    """Путь к Photoshop.exe из реестра — самый надёжный способ.

    Photoshop всегда прописывает себя в Classes\\Photoshop.Application\\CLSID,
    и путь там настоящий, независимо от года в имени папки.
    """
    try:
        import winreg
    except ImportError:
        return None
    key_path = r"SOFTWARE\Classes\Photoshop.Application\CLSID"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            clsid = str(winreg.QueryValueEx(key, "")[0])
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            rf"SOFTWARE\Classes\CLSID\{clsid}\LocalServer32") as key:
            raw = str(winreg.QueryValueEx(key, "")[0])
    except OSError:
        return None
    # В реестре строка вида  "C:\...\Photoshop.exe" /Automation
    path = Path(raw.strip().strip('"').split('"')[0].split(" /")[0].strip())
    return path if path.is_file() else None


def photoshop_from_folders() -> list[Path]:
    """Известные места: Program Files и папки Photo на других дисках."""
    found: list[Path] = []
    for root in COMMON_ROOTS:
        if not root.is_dir():
            continue
        if root.name.lower() == "adobe":
            found += sorted(root.glob("Adobe Photoshop */Photoshop.exe"))
        else:
            found += sorted(root.glob("Adobe Photoshop */Photoshop.exe"))
            found += sorted(root.glob("*/Photoshop.exe"))
    unique: list[Path] = []
    for path in found:
        if path.is_file() and path not in unique:
            unique.append(path)
    return unique


def photoshop_candidates() -> list[Path]:
    """Все найденные Photoshop: сначала указанный в ini, потом остальные."""
    out: list[Path] = []
    configured = config.get("photoshop", "path").strip() or \
        os.environ.get("PASSPORT_PHOTOSHOP", "").strip()
    if configured:
        path = Path(configured.strip().strip('"'))
        out.append(path if path.is_file() else path / "Photoshop.exe")
    registry = photoshop_from_registry()
    if registry is not None:
        out.append(registry)
    out += photoshop_from_folders()
    unique: list[Path] = []
    for path in out:
        if path not in unique:
            unique.append(path)
    return unique


def photoshop_exe() -> str:
    for path in photoshop_candidates():
        if path.is_file():
            return str(path)
    return ""


def scripts_dirs() -> list[tuple[Path, bool]]:
    """Папки скриптов Photoshop: системные и пользовательские.

    Возвращает пары (папка, системная ли она). Пользовательские создаются: права
    на них не нужны, а Photoshop подхватывает скрипты и оттуда.
    """
    dirs: list[tuple[Path, bool]] = []
    appdata = Path.home() / "AppData/Roaming/Adobe"

    for exe in photoshop_candidates():
        system_dir = exe.parent / "Presets" / "Scripts"
        if system_dir.parent.parent.is_dir():
            dirs.append((system_dir, True))
        plain = exe.parent / "Scripts"
        if plain.is_dir():
            dirs.append((plain, True))

    if appdata.is_dir():
        for folder in sorted(appdata.glob("Adobe Photoshop *")):
            dirs.append((folder / "Presets" / "Scripts", False))
            dirs.append((folder / "Scripts", False))

    unique: list[tuple[Path, bool]] = []
    for path, system in dirs:
        if (path, system) not in unique:
            unique.append((path, system))
    return unique


# ── Установка ────────────────────────────────────────────────────────────────


def python_launcher() -> str:
    """Интерпретатор для запуска из исходников — желательно без окна консоли.

    Запуск идёт через start, и консольное приложение на Windows при этом
    получает своё окно, которое висит до конца работы программы. pythonw.exe —
    тот же интерпретатор без окна; вывод программа пишет в журнал сама.
    """
    python = Path(sys.executable)
    windowless = python.with_name("pythonw.exe")
    return str(windowless if windowless.is_file() else python)


def paths_text(work: Path) -> str:
    """Что пишем рядом со скриптом: чем запускать программу и где обмен."""
    lines = []
    command = config.self_command()
    if getattr(sys, "frozen", False):
        lines.append(f"exe={Path(command[0]).as_posix()}")
    else:
        lines.append(f"python={Path(python_launcher()).as_posix()}")
        lines.append(f"program={Path(command[1]).as_posix()}")
    lines.append(f"work={work.as_posix()}")
    auto = config.auto_size()
    if auto:
        lines.append(f"auto_size={auto}")
    return "\n".join(lines) + "\n"


def install(verbose: bool = True, report: list[str] | None = None) -> int:
    """Копирует скрипт в найденные Photoshop.

    Возвращает 0, если скрипт лёг хотя бы куда-то. Подробности идут в отчёт:
    report — список, который заполняется построчно (его показывает окно), плюс
    печать в консоль при verbose и файл passport_work\\install.log. В собранном
    exe консоли нет, поэтому молча пройти мимо ошибки нельзя.
    """
    lines: list[str] = []
    source = jsx_source()
    if source is None:
        lines.append(f"Не найден {SOURCE_JSX_NAME}: положите его рядом с "
                     f"программой или укажите путь в ini, [paths] jsx_source.")
        return _finish(lines, verbose, 1, report)

    work = config.work_dir()
    text = paths_text(work)
    targets = scripts_dirs()
    if not targets:
        lines.append("Не нашёл папку скриптов Photoshop.")
        lines.append("Укажите путь к Photoshop.exe в ini, [photoshop] path, "
                     "и запустите установку снова.")
        return _finish(lines, verbose, 1, report)

    lines.append(f"Скрипт:  {source}")
    lines.append(f"Запуск:  {text.splitlines()[0]}")
    lines.append(f"Обмен:   {work}")
    lines.append("")
    installed = 0
    system_blocked = False
    for directory, system in targets:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, directory / JSX_NAME)
            (directory / PATHS_NAME).write_text(text, encoding="utf-8")
            installed += 1
            lines.append(f"  установлено: {directory}")
        except PermissionError:
            system_blocked = system
            lines.append(f"  нет прав на запись: {directory}")
        except OSError as exc:
            lines.append(f"  не удалось: {directory} — {exc}")

    lines.append("")
    if installed:
        lines.append(f"Готово: скрипт в {installed} папках. В Photoshop: панель "
                     "Действия → новое действие → «выполнить сценарий» → "
                     f"выбрать {JSX_NAME} → «Записать клавишу».")
    if system_blocked:
        lines += [
            "",
            "Системную папку в Program Files не удалось записать — нужны права "
            "администратора. Скрипт установлен в папку пользователя, её Photoshop "
            "тоже видит. Если хотите именно в Program Files, запустите установку "
            "от имени администратора.",
        ]
    elif not installed:
        lines.append("Ни в одну папку записать не удалось.")
    return _finish(lines, verbose, 0 if installed else 1, report)


def _finish(lines: list[str], verbose: bool, code: int,
            report: list[str] | None) -> int:
    if report is not None:
        report.extend(lines)
    text = "\n".join(lines)
    if verbose:
        print(text)
    try:
        work = config.work_dir()
        work.mkdir(parents=True, exist_ok=True)
        (work / "install.log").write_text(text + "\n", encoding="utf-8")
    except OSError:
        pass
    if verbose:
        print()
        print(f"Подробности: {config.work_dir() / 'install.log'}")
    return code


def installed_paths(jsx_dir: Path) -> dict[str, str]:
    """Читает passport_paths2.txt из папки скрипта — для проверок."""
    text = (jsx_dir / PATHS_NAME).read_text(encoding="utf-8-sig", errors="replace")
    out: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip():
            out[key.strip()] = value.strip()
    return out
