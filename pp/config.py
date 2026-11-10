"""Настройки программы — всё в passport.ini рядом с ней.

Файл необязательный: если его нет, программа создаёт рядом с собой готовый
шаблон с русскими комментариями и работает по встроенным значениям. Ни одна
цифра не зашита в код — правки из ini видны сразу, без пересборки exe.

Что где лежит:

    [general]    формат сохранения, качество, суффикс и папка результата
    [paths]      папки работы, моделей и шаблонов (пусто = рядом с программой)
    [photoshop]  путь к Photoshop.exe и размер без вопросов
    [geometry]   ширина лица и положение головы: запас над волосами, границы
                 подбородка, доли кадра
    [mvd]        нормы МВД для отчёта
    [tilt]       веса линий, по которым считается наклон головы
    [round_face] поправки для круглой головы
    [sizes]      список размеров фотографий и сами размеры секциями [sizes.ID]
"""

from __future__ import annotations

import configparser
import os
import sys
from pathlib import Path

# 762 ppi — ровно 30 пикселей на миллиметр, поэтому 37 × 47 мм = 1110 × 1410 px
PPI = 762

INI_NAME = "passport.ini"

# Папка, где лежит сама программа. В собранном exe это папка exe, при запуске
# из исходников — папка проекта. Рядом с ней живёт ini.
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) \
    else Path(__file__).resolve().parent.parent
# Папка с ресурсами, вшитыми в exe. В обычном запуске она совпадает с APP_DIR.
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))

TEMPLATE_INI = """\
; Настройки программы «Фото на документ по требованиям МВД».
; Файл создан при первом запуске. Меняйте значения и запускайте программу
; снова — пересобирать exe не нужно.
; Везде, где написано «пусто», программа сама возьмёт папку рядом с собой.

[general]
; Формат сохранения: JPEG, PSD или TIFF.
save_format = JPEG
; Качество JPEG: 0…12, 12 — максимум.
jpeg_quality = 12
; Дописывается к имени исходника. Можно оставить пустым.
output_suffix = _3,7x4,7см
; Папка результата внутри папки исходника. Пусто — рядом с исходником.
output_subdir =
; Разрешение холста: 762 ppi = ровно 30 px на мм.
ppi = 762
; Сторона превью для распознавания. Точек от этого не страдает.
detect_max_side = 2000
; Насколько уверенно ищется лицо: 0…1.
face_detect_threshold = 0.4
; Показывать окно с отчётом после сборки: 1 — да, 0 — нет.
show_report = 1
; Через сколько секунд окно отчёта закрывается само. Пока оно открыто, живёт и
; процесс — Photoshop ждёт его результата. 0 — не закрывать (тогда закрывайте
; окно сами, иначе экземпляры программы будут копиться).
report_timeout_sec = 90

[paths]
; Папка обмена файлами с Photoshop. Пусто — рядом с программой.
work_dir =
; Папка с моделями det_10g.onnx и 2d106det.onnx. Пусто — рядом с программой.
models_dir =
; Папка с шаблонами .psd. Пусто — рядом с программой.
templates_dir =

[photoshop]
; Путь к Photoshop.exe. Он нужен установщику скрипта: passport.exe install
; сам положит скрипт в папку Presets\\Scripts этого Photoshop.
path =
; Размер без вопросов — например 37x47. Тогда окно выбора не показывается,
; а Photoshop работает без своих модальных окон. Пусто — размер выбираете вы.
auto_size =

[geometry]
; Ширина лица по скулам — доля ширины кадра. То же и для размеров, где в
; секции [sizes.ID] не задано своё значение face_width_mm.
face_width_frac = 0.5000
; Подбородок снизу кадра — доля высоты кадра. Для основного размера своё
; значение в миллиметрах, здесь оно как запасной для остальных размеров.
chin_from_bottom_frac = 0.2830
; Центр лица по X — доля ширины кадра. На архиве из 81 готовой фотографии лицо
; стоит ровно посередине: смещение середина −0,06 мм, разброс −0,80…+0,43.
face_center_x_frac = 0.5000
; Насколько «макушка → подбородок» больше ширины лица. В наборе 106 точек
; нет точки на лбу, поэтому макушка оценивается по этой доле. Эта оценка нужна
; теперь только для отчёта: положение головы задаётся волосами, см. headroom_mm.
crown_ratio = 1.66
; Сколько места оставлять над волосами — главная величина положения головы.
; Взята с ваших готовых фотографий: медиана 3,1 мм, у 75 из 81 снимка отклонение
; от 3,1 мм не больше 1 мм. Остальные размеры пересчитываются пропорционально
; высоте кадра, а в секции [sizes.ID] можно задать своё значение.
headroom_mm = 3.1
; Подбородок не опускается ниже этого расстояния до нижнего края кадра. Нужно,
; потому что у людей с пышной причёской волосы занимают место макушки: держать
; запас в 3,1 мм ради них — значит увести подбородок к самому краю кадра. В
; архиве подбородок опускается до 10,2 мм, и ни разу не ниже.
chin_floor_mm = 11.0
; …и не поднимается выше этого. Обратная сторона того же правила: у человека с
; короткой стрижкой волосы близко к макушке, и при строгих 3,1 мм подбородок
; уехал бы к верху кадра. В архиве подбородок ни разу не выше 15,7 мм.
chin_ceiling_mm = 15.7

[mvd]
; Нормы ГОСТ Р 5103 для кадра 37 × 47 мм. Остальные размеры пересчитываются
; пропорционально своему кадру.
width_min_mm = 17.0
width_max_mm = 21.0
height_min_mm = 30.0
height_max_mm = 33.0

[tilt]
; Наклон головы считается как взвешенная медиана отклонений шести линий.
; Чем больше вес, тем сильнее линия тянет результат. Лицо выравнивается прежде
; всего по овалу: рты и брови у живых людей кривые чаще всего.
; Порядок: глаза, рот, брови, овал лица, брови→подбородок, переносица→подбородок.
weights = 1.2, 0.4, 0.4, 3.0, 0.4, 0.4
; Углы, при которых каждая линия считается ровной. Получены усреднением ваших
; лиц после принудительного выставления линии глаз в ноль. Менять только если
; понимаете, что делаете.
level_angles = 0.0, -0.5675, -0.4195, -90.3303, 179.3845, 179.2722

[round_face]
; У полного круглолицкого человека та же ширина лица означает более высокую
; голову. Для таких лиц программа делает лицо чуть шире. Лысину по точкам не
; видно, поэтому круглота ловится сразу по трём отношениям, и все три должны быть
; не больше своих порогов:
;   овал / ширина лица         — высота лица близка к ширине
;   подбородок→глаза / ширина  — глаза низко, лицо «сплющено»
;   расстояние глаз / ширина    — у широкого круглого лица глаза отнесены от
;                                 краёв, то есть доля мала
enable = 1
; Что делать с поправкой: auto — определять по лицу, yes — всегда считать голову
; круглой, no — не делать поправку. В окне выбора это поле запоминается сюда.
mode = auto
; Пороги проверены на архиве готовых фотографий: под них попадают 6 снимков из
; 81, и на всех шести лица действительно круглые и полные. У этих шести лицо
; в кадре шире — 18,66 мм против 18,38 мм у остальных.
oval_ratio_max = 0.830
chin_eye_ratio_max = 0.790
eye_ratio_max = 0.436
; Поправка по ширине, мм. Подтверждается архивом: у круглых лиц ширина 18,66 мм
; против 18,38 мм у остальных.
width_add_mm = 0.5
; Вертикальная часть поправки. Раньше голова поднималась на chin_up_mm, потому
; что оценочная макушка у круглой головы ниже нужной. Теперь голову ставит не
; оценочная макушка, а сами волосы ([geometry] headroom_mm), поднимать больше
; нечего: у круглых лиц в архиве запас над волосами 3,18 мм — как у всех.
chin_up_mm = 0.0

[sizes]
; Порядок в окне выбора и состав списка. Формат добавляется и убирается здесь
; же, руками: допишите или удалите секцию [sizes.ИМЯ] ниже — программа читает
; файл целиком, и удалённый формат больше не появится. Свой размер можно также
; добавить кнопкой в самом окне выбора.
; Имя в order должно совпадать с тем, что после «sizes.» в заголовке секции.
; Чтобы формат был в списке, но не выбран по умолчанию, оставьте его в order
; последним.
order = 37x47, 30x40, 35x45, 37x37

; Секция размера. Обязательны только width_mm и height_mm (в миллиметрах).
; Остальное необязательно:
;   label             — подпись в окне выбора, пусто — имя секции
;   face_width_mm     — лицо по скулам; пусто — доля кадра из [geometry]
;   chin_from_bottom_mm — подбородок снизу кадра; пусто — доля из [geometry]
;   suffix            — подпись к имени файла результата, пусто — «3,7x4,7см»
;   template          — .psd из папки templates, пусто — новый пустой холст

[sizes.37x47]
label = 3,7 × 4,7 см (основной)
width_mm = 37
height_mm = 47
face_width_mm = 18.5
chin_from_bottom_mm = 13.3
template = 3,7x4,7.psd

[sizes.30x40]
label = 3,0 × 4,0 см
width_mm = 30
height_mm = 40

[sizes.35x45]
label = 3,5 × 4,5 см (МВД)
width_mm = 35
height_mm = 45

[sizes.37x37]
label = 3,7 × 3,7 см (квадрат)
width_mm = 37
height_mm = 37
"""

DEFAULTS: dict[str, dict[str, str]] = {
    "general": {
        "save_format": "JPEG", "jpeg_quality": "12",
        "output_suffix": "_3,7x4,7см", "output_subdir": "",
        "ppi": str(PPI), "detect_max_side": "2000",
        "face_detect_threshold": "0.4", "show_report": "1",
        "report_timeout_sec": "90",
    },
    "paths": {"work_dir": "", "models_dir": "", "templates_dir": ""},
    "photoshop": {"path": "", "auto_size": ""},
    "geometry": {
        "face_width_frac": "0.5000", "chin_from_bottom_frac": "0.2830",
        "face_center_x_frac": "0.5000", "crown_ratio": "1.66",
        "headroom_mm": "3.1", "chin_floor_mm": "11.0",
        "chin_ceiling_mm": "15.7",
    },
    "mvd": {
        "width_min_mm": "17.0", "width_max_mm": "21.0",
        "height_min_mm": "30.0", "height_max_mm": "33.0",
    },
    "tilt": {
        "weights": "1.2, 0.4, 0.4, 3.0, 0.4, 0.4",
        "level_angles": "0.0, -0.5675, -0.4195, -90.3303, 179.3845, 179.2722",
    },
    "round_face": {
        "enable": "1", "mode": "auto",
        "oval_ratio_max": "0.830", "chin_eye_ratio_max": "0.790",
        "eye_ratio_max": "0.436",
        "width_add_mm": "0.5", "chin_up_mm": "0.0",
    },
"sizes": {"order": "37x47, 30x40, 35x45, 37x37"},
}

# Готовые размеры зашиты в код как запасной вариант: если ini потерялся или в
# нём только часть секций, программа всё равно предложит эти четыре.
SIZE_DEFAULTS: dict[str, dict[str, str]] = {
    "sizes.37x47": {
        "label": "3,7 × 4,7 см (основной)",
        "width_mm": "37", "height_mm": "47",
        "face_width_mm": "18.5", "chin_from_bottom_mm": "13.3",
        "template": "3,7x4,7.psd",
    },
    "sizes.30x40": {
        "label": "3,0 × 4,0 см",
        "width_mm": "30", "height_mm": "40",
    },
    "sizes.35x45": {
        "label": "3,5 × 4,5 см (МВД)",
        "width_mm": "35", "height_mm": "45",
    },
    "sizes.37x37": {
        "label": "3,7 × 3,7 см (квадрат)",
        "width_mm": "37", "height_mm": "37",
    },
}

# Базовый размер: его значения геометрии заданы числами, а не долями кадра.
BASE_PRESET_ID = "37x47"

_parser: configparser.ConfigParser | None = None
_ini_path: Path | None = None
_ini_error: str = ""


# ── Чтение ini ──────────────────────────────────────────────────────────────


def ini_path() -> Path:
    """Где искать (и где создавать) файл настроек.

    Рядом с exe переменная PASSPORT_INI переопределяет путь — так один и тот же
    exe работает с разными настройками на разных студиях.
    """
    override = os.environ.get("PASSPORT_INI", "").strip()
    return Path(override) if override else APP_DIR / INI_NAME


def _ensure_ini(path: Path) -> None:
    if path.exists():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(TEMPLATE_INI, encoding="utf-8-sig")
    except OSError:
        pass   # нет права писать — работаем на встроенных значениях


def _new_parser(sections: dict[str, dict[str, str]]) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None)
    for section, values in sections.items():
        cp[section] = dict(values)
    return cp


def parser() -> configparser.ConfigParser:
    """Разобранный ini. Создаёт и читает файл при первом обращении.

    Уже существующий файл — единственный источник правды: в разбор НЕ подмешиваются
    зашитые значения. Иначе удалённую вручную секцию [sizes.*] программа каждый
    раз возвращала бы сама, и форматы нельзя было бы ни убрать, ни добавить.
    Отсутствующие значения подставляются по одному при чтении (DEFAULTS),
    а если размеров в файле не осталось вовсе — берутся встроенные.
    """
    global _parser, _ini_path, _ini_error
    if _parser is not None:
        return _parser
    path = ini_path()
    # Шаблон создаём ДО чтения: иначе в первый запуск файл появился бы, но
    # разобран не был бы — и размеры из него не попали бы в список.
    _ensure_ini(path)
    cp = configparser.ConfigParser(interpolation=None)
    if path.exists():
        try:
            # utf-8-sig: файл мы сами пишем с BOM, чтобы «Блокнот» на Windows
            # не гадал кодировку, а редакторы без BOM тоже не мешали.
            cp.read(path, encoding="utf-8-sig")
        except (OSError, configparser.Error) as exc:
            # Ошибка в ini молча уводила программу на встроенные значения, и
            # правки пользователя выглядели бесполезными. Текст с ошибкой
            # показывается при запуске (ini_error), файл не трогаем — иначе
            # нечаянная ошибка в правке стёрла бы все настройки.
            _ini_error = f"{path.name}: {exc}"
            cp = _new_parser({s: dict(v) for s, v in DEFAULTS.items()})
            cp.read_string(TEMPLATE_INI)
    _parser = cp
    _ini_path = path
    return cp


def ini_error() -> str:
    """Текст проблемы с ini, если файл не читается. Пусто — всё в порядке."""
    parser()
    return _ini_error


def get(section: str, option: str, default: str | None = None) -> str:
    cp = parser()
    if section in cp and option in cp[section]:
        return cp[section][option].strip()
    return DEFAULTS.get(section, {}).get(option, default or "")


def get_float(section: str, option: str, default: float) -> float:
    try:
        return float(get(section, option).replace(",", "."))
    except ValueError:
        return default


def get_int(section: str, option: str, default: int) -> int:
    try:
        return int(round(get_float(section, option, float(default))))
    except ValueError:
        return default


def get_bool(section: str, option: str, default: bool) -> bool:
    raw = get(section, option).lower()
    if raw in ("1", "да", "true", "on", "yes"):
        return True
    if raw in ("0", "нет", "false", "off", "no"):
        return False
    return default


def get_floats(section: str, option: str, default: list[float]) -> list[float]:
    """Список чисел из строки «1.2, 0.4, 0.4, 3.0, 0.4, 0.4»."""
    raw = get(section, option).replace(";", ",")
    out: list[float] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(float(chunk.replace(",", ".")))
        except ValueError:
            return list(default)
    return out or list(default)


def set_value(section: str, option: str, value) -> None:
    cp = parser()
    if section not in cp:
        cp.add_section(section)
    cp.set(section, option, str(value))


def _merged_text(original: str, cp: configparser.ConfigParser) -> str:
    """Пересобирает текст ini с новыми значениями, сохраняя комментарии.

    configparser при записи выбрасывает все комментарии и переставляет секции, а
    этот файл пользователь правит руками: русские пояснения к каждому полю —
    половина его ценности. Поэтому обновляются только сами строки «ключ =
    значение», а комментарии, порядок секций и пустые строки остаются как были.
    Новые ключи дописываются в свою секцию, новые секции — в конец файла.
    """
    wanted = {section: dict(cp[section]) for section in cp.sections()}
    present = _sections_and_keys(original)

    out: list[str] = []
    current: str | None = None
    added: list[str] = []          # ключи, дописываемые в конец текущей секции
    for line in original.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            out += added
            added = []
            name = stripped[1:-1].strip()
            current = name if name in wanted else None
            if current is not None:
                already = present.get(name, set())
                added = [f"{key} = {value}"
                         for key, value in wanted[current].items()
                         if key not in already]
            out.append(line)
            continue
        if current and "=" in stripped and stripped[0] not in ";#[(":
            key = stripped.split("=", 1)[0].strip()
            if key in wanted[current]:
                out.append(f"{key} = {wanted[current][key]}")
                continue
        out.append(line)
    out += added

    for name, values in wanted.items():
        if name in present:
            continue
        out.append("")
        out.append(f"[{name}]")
        out += [f"{key} = {value}" for key, value in values.items()]
    return "\n".join(out) + "\n"


def _sections_and_keys(text: str) -> dict[str, set[str]]:
    """Какие секции и ключи уже есть в тексте ini — свои, не из разбора.

    Нужен, чтобы новый ключ дописывался один раз, а не рядом со старым, и чтобы
    секция, удалённая пользователем, не вернулась при первой же записи.
    """
    found: dict[str, set[str]] = {}
    current: set[str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = found.setdefault(stripped[1:-1].strip(), set())
        elif current is not None and "=" in stripped and stripped[0] not in ";#[(":
            current.add(stripped.split("=", 1)[0].strip())
    return found


def save() -> None:
    """Записать изменённые значения в ini рядом с программой.

    В файл, который не удалось разобрать, не пишем: иначе одна опечатка в
    редакторе затёрла бы все настройки. О таком файле сообщается при запуске.
    """
    path = _ini_path or ini_path()
    if _ini_error:
        return
    try:
        original = path.read_text(encoding="utf-8-sig")
    except OSError:
        original = ""
    text = _merged_text(original, parser())
    with path.open("w", encoding="utf-8-sig", newline="\n") as f:
        f.write(text)


# ── Папки ───────────────────────────────────────────────────────────────────


def _dir_option(option: str, fallback: Path) -> Path:
    raw = get("paths", option)
    return Path(raw) if raw else fallback


def work_dir() -> Path:
    return _dir_option("work_dir", APP_DIR / "passport_work")


def models_dir() -> Path:
    return _dir_option("models_dir", BUNDLE_DIR / "models")


def templates_dir() -> Path:
    return _dir_option("templates_dir", BUNDLE_DIR / "templates")


def project_dir() -> Path:
    """Папка с примерами и шаблонами для проверок. В сборке exe её нет."""
    return APP_DIR


def samples_dir() -> Path:
    """Где лежат ваши исходники source1…6 для проверок.

    В папке программы их может не быть — тогда берём родительскую папку: в
    разработке программа живёт подпапкой рядом с примерами.
    """
    here = APP_DIR
    if (here / "source1.jpg").exists():
        return here
    parent = here.parent
    return parent if (parent / "source1.jpg").exists() else here


DET_MODEL = models_dir() / "det_10g.onnx"
LM_MODEL = models_dir() / "2d106det.onnx"

SETTINGS_FILE = ini_path()


# ── Прочие числа, нужные без разбора ini ─────────────────────────────────────

PX_PER_MM = get_float("general", "ppi", PPI) / 25.4

FACE_WIDTH_FRAC = get_float("geometry", "face_width_frac", 0.5)
CHIN_FROM_BOTTOM_FRAC = get_float("geometry", "chin_from_bottom_frac", 0.2830)
FACE_CENTER_X_FRAC = get_float("geometry", "face_center_x_frac", 0.5)
CROWN_RATIO_MEAN = get_float("geometry", "crown_ratio", 1.66)
# Запас над волосами и нижняя граница подбородка заданы для базового кадра
# (37 × 47 мм) и дальше пересчитываются пропорционально высоте — так же, как
# нормы МВД в norm_band.
HEADROOM_MM = get_float("geometry", "headroom_mm", 3.1)
CHIN_FLOOR_MM = get_float("geometry", "chin_floor_mm", 11.0)

MVD_WIDTH_MIN_MM = get_float("mvd", "width_min_mm", 17.0)
MVD_WIDTH_MAX_MM = get_float("mvd", "width_max_mm", 21.0)
MVD_HEIGHT_MIN_MM = get_float("mvd", "height_min_mm", 30.0)
MVD_HEIGHT_MAX_MM = get_float("mvd", "height_max_mm", 33.0)

TILT_WEIGHTS = get_floats("tilt", "weights", [1.2, 0.4, 0.4, 3.0, 0.4, 0.4])
LEVEL_ANGLES = get_floats("tilt", "level_angles",
                          [0.0, -0.5675, -0.4195, -90.3303, 179.3845, 179.2722])
TILT_NAMES = ["линия глаз", "линия рта", "линия бровей", "овал лица",
              "брови→подбородок", "переносица→подбородок"]

SAVE_FORMAT = get("general", "save_format", "JPEG").upper()
JPEG_QUALITY = get_int("general", "jpeg_quality", 12)
SHOW_REPORT = get_bool("general", "show_report", True)
OUTPUT_SUFFIX = get("general", "output_suffix", "_3,7x4,7см")
OUTPUT_SUBDIR = get("general", "output_subdir", "")
DETECT_MAX_SIDE = get_int("general", "detect_max_side", 2000)
FACE_DETECT_THRESHOLD = get_float("general", "face_detect_threshold", 0.4)

ROUND_FACE = {
    "enable": get_bool("round_face", "enable", True),
    "oval_ratio_max": get_float("round_face", "oval_ratio_max", 0.830),
    "chin_eye_ratio_max": get_float("round_face", "chin_eye_ratio_max", 0.790),
    "eye_ratio_max": get_float("round_face", "eye_ratio_max", 0.436),
    "width_add_mm": get_float("round_face", "width_add_mm", 0.5),
    "chin_up_mm": get_float("round_face", "chin_up_mm", 0.0),
}

# Смешанное имя — чтобы старые скрипты проверки продолжали работать.
PROJECT_DIR = APP_DIR
PRESETS: dict[str, dict] = {}


def headroom_mm() -> float:
    """Запас над волосами, мм — читается из ini на каждый вызов.

    Отдельной функцией, а не константой модуля, по той же причине, что и веса
    наклона: правка ini видна сразу, без перезапуска Photoshop.
    """
    return get_float("geometry", "headroom_mm", 3.1)


def chin_floor_mm() -> float:
    """Подбородок не опускается ниже этого расстояния до нижнего края, мм."""
    return get_float("geometry", "chin_floor_mm", 11.0)


def chin_ceiling_mm() -> float:
    """Подбородок не поднимается выше этого расстояния до низа кадра, мм.

    Обратная сторона headroom_mm: у человека с короткой стрижкой волосы близко к
    макушке, и при строгих 3,1 мм над волосами подбородок уехал бы к верху кадра.
    """
    return get_float("geometry", "chin_ceiling_mm", 15.7)


def tilt_weights() -> list[float]:
    """Весы линий при выравнивании наклона — читаются из ini на каждый вызов."""
    return get_floats("tilt", "weights", [1.2, 0.4, 0.4, 3.0, 0.4, 0.4])


def level_angles() -> list[float]:
    """Углы «ровного лица» по каждой линии — тоже из ini."""
    return get_floats("tilt", "level_angles",
                      [0.0, -0.5675, -0.4195, -90.3303, 179.3845, 179.2722])


def round_face_settings() -> dict:
    """Поправки для круглой головы: по умолчанию берутся из ini."""
    return {
        "enable": get_bool("round_face", "enable", True),
"oval_ratio_max": get_float("round_face", "oval_ratio_max", 0.830),
        "chin_eye_ratio_max": get_float("round_face", "chin_eye_ratio_max", 0.790),
        "eye_ratio_max": get_float("round_face", "eye_ratio_max", 0.436),
        "width_add_mm": get_float("round_face", "width_add_mm", 0.5),
        "chin_up_mm": get_float("round_face", "chin_up_mm", 0.0),
    }


# ── Пресеты размеров ────────────────────────────────────────────────────────


def _size_suffix(width_mm: float, height_mm: float) -> str:
    """Имя размера для имени файла: 3,7x4,7см, 3x4см. Размер в сантиметрах."""
    def cm(value_mm: float) -> str:
        return f"{value_mm / 10:g}".replace(".", ",")

    return f"{cm(width_mm)}x{cm(height_mm)}см"


def _clean(value: str, default: str) -> str:
    return default if value is None else value.strip()


def _number(raw: dict, key: str, default: float | None = None) -> float | None:
    """Число из секции размера. Пусто или мусор — берём default."""
    value = _clean(raw.get(key), "")
    if not value:
        return default
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return default


def _base_height(cp: configparser.ConfigParser) -> float:
    """Высота базового кадра, мм — к ней привязаны запас над волосами и нижняя
    граница подбородка. Читается напрямую, без сбора пресета: иначе получилась бы
    рекурсия на базовом размере."""
    section = f"sizes.{BASE_PRESET_ID}"
    raw = cp[section] if section in cp else SIZE_DEFAULTS.get(section, {})
    return _number(raw, "height_mm") or 47.0


def _build_preset(size_id: str,
                  cp: configparser.ConfigParser | None = None) -> dict | None:
    cp = cp if cp is not None else parser()
    section = f"sizes.{size_id}"
    if section not in cp:
        return None
    raw = cp[section]
    width = _number(raw, "width_mm")
    height = _number(raw, "height_mm")
    if not width or not height or width <= 0 or height <= 0:
        return None
    ppi = get_float("general", "ppi", PPI)
    # Лицо и подбородок можно задать для конкретного размера в миллиметрах, а
    # можно не задавать — тогда берутся доли кадра из [geometry].
    face_width = _number(raw, "face_width_mm")
    chin = _number(raw, "chin_from_bottom_mm")
    # Запас над волосами и нижняя граница подбородка заданы в [geometry] для
    # базового кадра и пересчитываются пропорционально высоте: у 3 × 4 см
    # headroom_mm = 3,1 × 40/47 = 2,64 мм. Своё значение можно задать в секции.
    scale = height / _base_height(cp)
    headroom = _number(raw, "headroom_mm")
    chin_floor = _number(raw, "chin_floor_mm")
    ceiling = _number(raw, "chin_ceiling_mm")
    return {
        "id": size_id,
        "label": _clean(raw.get("label"), size_id),
        "width_mm": width,
        "height_mm": height,
        "ppi": ppi,
        "template": _clean(raw.get("template"), ""),
        "suffix": _clean(raw.get("suffix"), _size_suffix(width, height)),
        "face_width_mm": face_width if face_width else FACE_WIDTH_FRAC * width,
        "chin_from_bottom_mm": chin if chin else CHIN_FROM_BOTTOM_FRAC * height,
        "headroom_mm": headroom if headroom else headroom_mm() * scale,
        "chin_ceiling_mm": ceiling if ceiling else chin_ceiling_mm() * scale,
        "chin_floor_mm": chin_floor if chin_floor else chin_floor_mm() * scale,
        "width_px": round(width * ppi / 25.4),
        "height_px": round(height * ppi / 25.4),
    }


def apply_settings() -> dict[str, dict]:
    """Действующие пресеты: все секции [sizes.*] плюс порядок из [sizes].

    Файл — единственный источник правды: удалённая из него секция формата
    программе не возвращается. Встроенные размеры подставляются только когда
    в файле не осталось ни одного (старый ini без секций или сломанный), и
    подставляются в память — в файл они не попадают.
    """
    cp = parser()
    presets: dict[str, dict] = {}
    for section in cp.sections():
        if section.startswith("sizes."):
            size_id = section[len("sizes."):].strip()
            if not size_id:
                continue
            preset = _build_preset(size_id, cp)
            if preset is not None:
                presets[size_id] = preset
    if not presets:
        builtin = _new_parser(SIZE_DEFAULTS)
        for section in builtin.sections():
            size_id = section[len("sizes."):]
            preset = _build_preset(size_id, builtin)
            if preset is not None:
                presets[size_id] = preset
    global PRESETS
    PRESETS = presets
    return presets


def preset_order(presets: dict[str, dict]) -> list[str]:
    """Порядок в меню: сначала явный из ini, потом остальные по алфавиту."""
    saved = [s.strip() for s in get("sizes", "order").split(",") if s.strip()]
    ordered = [s for s in saved if s in presets]
    ordered += sorted(s for s in presets if s not in ordered)
    return ordered


def add_preset(width_mm: float, height_mm: float, label: str = "",
               preset: dict | None = None) -> dict:
    """Добавляет произвольный размер в ini и возвращает его описание.

    preset, если задан, кладётся в ini как есть — вместе с миллиметрами лица и
    подбородка. Сохраняется сразу: пользователь ввёл новый формат — он должен
    пережить перезапуск программы.
    """
    size_id = f"{width_mm:g}x{height_mm:g}".replace(".", ",")
    section = f"sizes.{size_id}"
    if section in parser():
        # Такой размер уже заведён в ini. Обновляем только отступы, если их
        # задали: подпись и размер кадра остаются прежними.
        if preset:
            for key in ("face_width_mm", "chin_from_bottom_mm"):
                if preset.get(key):
                    parser().set(section, key,
                                 f"{float(preset[key]):g}".replace(".", ","))
            save()
            return apply_settings()[size_id]
        return apply_settings()[size_id]
    parser()[section] = {
        "label": label or (preset or {}).get("label")
        or f"{width_mm:g} × {height_mm:g} мм (свой размер)",
        "width_mm": f"{width_mm:g}",
        "height_mm": f"{height_mm:g}",
    }
    if preset:
        for key in ("face_width_mm", "chin_from_bottom_mm"):
            if preset.get(key):
                parser().set(section, key,
                             f"{float(preset[key]):g}".replace(".", ","))
    current = get("sizes", "order")
    ids = [s.strip() for s in current.split(",") if s.strip()]
    if size_id not in ids:
        ids.append(size_id)
        set_value("sizes", "order", ", ".join(ids))
    save()
    return apply_settings()[size_id]


def custom_preset(width_mm: float, height_mm: float, ppi: float | None = None,
                  face_width_mm: float | None = None,
                  chin_from_bottom_mm: float | None = None) -> dict:
    """Пресет для произвольного размера.

    Лицо и подбородок можно задать в миллиметрах прямо здесь — это то, что
    вводится в окне выбора. Не заданы — берутся доли кадра из [geometry].
    """
    width = float(str(width_mm).replace(",", "."))
    height = float(str(height_mm).replace(",", "."))
    base = _build_preset(BASE_PRESET_ID) or apply_settings().get(BASE_PRESET_ID)
    base_height = (base or {}).get("height_mm") or 47.0
    scale = height / base_height
    p = {
        "id": f"{width:g}x{height:g}",
        "label": f"{width:g} × {height:g} мм (свой размер)",
        "width_mm": width,
        "height_mm": height,
        "ppi": ppi or get_float("general", "ppi", PPI),
        "template": (base or {}).get("template", ""),
        "suffix": _size_suffix(width, height),
        "face_width_mm": face_width_mm or FACE_WIDTH_FRAC * width,
        "chin_from_bottom_mm": chin_from_bottom_mm or CHIN_FROM_BOTTOM_FRAC * height,
        "headroom_mm": headroom_mm() * scale,
        "chin_ceiling_mm": chin_ceiling_mm() * scale,
        "chin_floor_mm": chin_floor_mm() * scale,
    }
    p["width_px"] = round(width * p["ppi"] / 25.4)
    p["height_px"] = round(height * p["ppi"] / 25.4)
    return p


# ── Photoshop ────────────────────────────────────────────────────────────────


def python_exe() -> str:
    """Интерпретатор, которым запущен сам модуль (надёжнее, чем искать python)."""
    return sys.executable or "python"


def self_command() -> list[str]:
    """Чем запускать программу: exe целиком или python со скриптом."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(APP_DIR / "passport.py")]


def auto_size() -> str:
    """Размер без вопросов из ini, если он там задан."""
    return get("photoshop", "auto_size").strip()



