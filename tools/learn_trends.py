"""Закономерности ваших готовых фотографий: где голова и сколько места над волосами.

    python tools\\learn_trends.py [папка] [куда положить csv]

Это продолжение разбора из analyse_archive.py. Там меряется только то, что видно
по точкам лица: ширина, подбородок, наклон. Про причёску там сказать нечего —
в наборе 106 точек нет ни макушки, ни волос. А в готовых фотографиях видно,
где начинаются волосы, и вот это как раз и решает, куда сдвигать снимок.

Что меряется дополнительно:

    макушка (оценка)  — то, на что сейчас смотрит программа: подбородок вверх на
                        crown_ratio × ширину лица. Анатомическая макушка.
    волосы             — верхний пиксель, отличный от фона. Реальная верхушка
                        головы вместе с причёской.
    запас над волосами — сколько миллиметров от края кадра до волос.
    Пышность причёски  — насколько волосы поднялись над анатомической оценкой
                        макушки. Это остаток, а не измерение: он зависит и от
                        ширины лица, и от положения подбородка, поэтому мерять
                        с ним корреляции бессмысленно. Настоящая величина —
                        две следующие, они снимаются с картинки и ни от чего
                        не зависят.
    высота волос        — от верхнего края волос до линии бровей. Это и есть
                        объём причёски: у гладко зачёсанных волос она мала, у
                        пышных — заметно больше.
    ширина волос        — самая широкая часть силуэта выше бровей минус ширина
                        лица. Пышная причёска шире головы.

Программа сейчас ставит голову по оценке макушки и подбородка, поэтому запас над
волосами у неё получается случайным: у кого-то 5 мм, у кого волосы упираются в
край. Разбор показывает, чего вы на самом деле ждёте.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pp import config, geometry
from pp.face import analyse_path
from analyse_archive import DEFAULT_DIR, analyse_one

# Фон снимаем с верхней и боковых кромок кадра: сверху и сбоку у паспортной
# фотографии всегда фон, а снизу могут быть плечи.
BORDER_ROWS = 2
BORDER_COLS = 2
# Порог «пиксель отличается от фона». Ниже начинает ловить шум JPEG, выше —
# слишком грубо для тёмных волос на сером фоне.
BG_DIFF = 28
# Сколько таких пикселей в строке считать «здесь что-то есть». Одна тёмная точка
# на миллион — мусор, полпроцента ширины кадра — уже волосы.
ROW_FRAC = 0.004

# Запас над волосами, который получается в архиве сам собой. Подставляется в
# тождество выше — как точка отсчёта, а не как правило программы.
HEADROOM_MM = 3.1


def foreground(image: np.ndarray) -> np.ndarray:
    """Маска «не фон»: попиксельно, по трём каналам сразу."""
    border = np.concatenate([
        image[:BORDER_ROWS].reshape(-1, 3),
        image[:, :BORDER_COLS].reshape(-1, 3),
        image[:, -BORDER_COLS:].reshape(-1, 3),
    ])
    background = np.median(border, axis=0)
    return np.abs(image.astype(np.int16) - background).max(axis=2) > BG_DIFF


def hair_top_row(mask: np.ndarray) -> int | None:
    """Номер первой сверху строки, где что-то отличается от фона.

    Возвращает None, если кадр весь «пустой» — такого в архиве не бывает, но
    проверка дешевле, чем падение на битой фотографии.
    """
    width = mask.shape[1]
    need = max(3, int(width * ROW_FRAC))
    hits = np.nonzero((mask > 0).sum(axis=1) > need)[0]
    return int(hits[0]) if hits.size else None


def widest_above(mask: np.ndarray, top: int, bottom: int) -> float:
    """Самая широкая строка между двумя высотами — ширина причёски, в px."""
    span = mask[top:max(top + 1, bottom)]
    if not span.size:
        return 0.0
    return float(max((row).sum() for row in span))


def analyse_photo(path: Path, px_per_mm: float, doc_h: int) -> dict | None:
    """Одна фотография: точки лица плюс верх и ширина волос."""
    row = analyse_one(path, px_per_mm, doc_h)
    if row is None:
        return None
    face, _ = analyse_path(path)
    brow_y = float(((face.lm106[geometry.IDX["brow_left"]]
                    + face.lm106[geometry.IDX["brow_right"]]) / 2.0)[1])
    measures = geometry.measure_face(face.lm106)

    with Image.open(path) as im:
        image = np.asarray(im.convert("RGB"))
    mask = foreground(image)
    top = hair_top_row(mask)
    if top is None:
        return None

    hair_height = (brow_y - top) / px_per_mm
    hair_width = widest_above(mask, top, int(brow_y)) / px_per_mm
    crown_from_bottom = (row["подбородок снизу, мм"]
                         + config.CROWN_RATIO_MEAN * row["ширина лица, мм"])
    row["запас над волосами, мм"] = round(top / px_per_mm, 2)
    row["высота волос, мм"] = round(hair_height, 2)
    row["ширина волос, мм"] = round(hair_width, 2)
    row["волосы шире лица, мм"] = round(hair_width - row["ширина лица, мм"], 2)
    row["макушка сверху, мм"] = round(preset_height_mm() - crown_from_bottom, 2)
    row["волосы выше макушки, мм"] = round(
        row["макушка сверху, мм"] - row["запас над волосами, мм"], 2)
    row["лицо от центра кадра, мм"] = round(
        (measures.center[0] - mask.shape[1] / 2.0) / px_per_mm, 2)
    row["бровь до подбородка, мм"] = round(measures.chin_to_brow / px_per_mm, 2)
    # Главный вопрос архива: голову держат по волосам или по подбородку?
    # Расстояния связаны тождеством
    #     низ кадра → подбородок → брови → волосы → верх кадра,
    # поэтому обе величины не могут быть заданы независимо, и корреляция между
    # ними ничего не доказывает. Проверяется это иначе: считаем, какой подбородок
    # получился бы, если бы держать постоянный запас над волосами. Отклонение
    # фактического подбородка от расчётного и есть свобода оператора.
    keep_hair = (preset_height_mm() - HEADROOM_MM - row["высота волос, мм"]
                 - row["бровь до подбородка, мм"])
    row["подбородок, если бы держать запас, мм"] = round(keep_hair, 2)
    row["свобода сдвига, мм"] = round(row["подбородок снизу, мм"] - keep_hair, 2)
    return row


def preset_height_mm() -> float:
    return config.apply_settings()[config.BASE_PRESET_ID]["height_mm"]


def describe(rows: list[dict], key: str) -> str:
    values = np.array([r[key] for r in rows], dtype=float)
    return (f"{values.min():7.2f} … {values.max():7.2f}   "
            f"среднее {values.mean():7.2f}   середина {np.median(values):7.2f}")


def band(values: np.ndarray, step: float) -> str:
    """Как распределены значения: сколько в каждом интервале."""
    edges = np.arange(np.floor(values.min() / step) * step,
                      np.ceil(values.max() / step) + step, step)
    counts, _ = np.histogram(values, bins=edges)
    return "  ".join(f"{edges[i]:.1f}…{edges[i + 1]:.1f}: {c}"
                     for i, c in enumerate(counts) if c)


def correlation(rows: list[dict], a: str, b: str) -> float:
    x = np.array([r[a] for r in rows], dtype=float)
    y = np.array([r[b] for r in rows], dtype=float)
    if x.std() == 0 or y.std() == 0:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def report(rows: list[dict], folder: Path) -> None:
    """Закономерности. Корреляции — только между независимыми величинами:
    «волосы выше макушки» остаток, в состав которого входят и подбородок, и
    ширина лица, поэтому коррелировать его с ними бессмысленно."""
    head = np.array([r["запас над волосами, мм"] for r in rows])
    hair_h = np.array([r["высота волос, мм"] for r in rows])
    hair_w = np.array([r["волосы шире лица, мм"] for r in rows])
    chin = np.array([r["подбородок снизу, мм"] for r in rows])
    width = np.array([r["ширина лица, мм"] for r in rows])

    print("\n  Где голова в кадре")
    print("  величина                 разброс              среднее   середина")
    print("  ------------------------ -------------------- --------- ---------")
    for key in ("запас над волосами, мм", "высота волос, мм",
                "волосы шире лица, мм", "макушка сверху, мм",
                "ширина лица, мм", "подбородок снизу, мм",
                "лицо от центра кадра, мм"):
        print(f"  {key:24s} {describe(rows, key)}")

    print(f"\n  запас над волосами: {band(head, 0.5)}")
    print(f"  высота волос:       {band(hair_h, 1.0)}")

    print("\n  Что с чем связано (только независимые величины)")
    print(f"  высота волос ↔ запас над волосами  {correlation(rows, 'высота волос, мм', 'запас над волосами, мм'):+.2f}")
    print(f"  высота волос ↔ подбородок снизу   {correlation(rows, 'высота волос, мм', 'подбородок снизу, мм'):+.2f}")
    print(f"  ширина волос ↔ запас над волосами {correlation(rows, 'волосы шире лица, мм', 'запас над волосами, мм'):+.2f}")
    print(f"  ширина лица  ↔ подбородок снизу   {correlation(rows, 'ширина лица, мм', 'подбородок снизу, мм'):+.2f}")
    print(f"  запас        ↔ подбородок снизу   {correlation(rows, 'запас над волосами, мм', 'подбородок снизу, мм'):+.2f}")

    busy_cut = float(np.percentile(hair_h, 75))
    print(f"\n  Пышная причёска (высота волос больше {busy_cut:.1f} мм — верхняя "
          f"четверть архива) против остальных")
    print(f"  {'':28s} {'пышная':>10s} {'остальные':>10s}")
    for key in ("запас над волосами, мм", "подбородок снизу, мм",
                "ширина лица, мм", "макушка сверху, мм"):
        busy = np.array([r[key] for r in rows if r["высота волос, мм"] > busy_cut])
        calm = np.array([r[key] for r in rows if r["высота волос, мм"] <= busy_cut])
        print(f"  {key:28s} {np.median(busy):10.2f} {np.median(calm):10.2f}")

    # Самое интересное: подчиняется ли запас над волосами одной величине, или
    # это просто «столько оставляют всегда».
    quiet = np.abs(head - np.median(head)) <= 1.0
    print(f"\n  Запас над волосами держится около {np.median(head):.1f} мм: "
          f"у {int(quiet.sum())} из {len(rows)} отклонение не больше 1 мм "
          f"(разброс {head[quiet].min():.1f}…{head[quiet].max():.1f}).")
    print(f"  Подбородок снизу: у {int((chin >= 13.0).sum())} из {len(rows)} "
          f"не ниже 13 мм, у {int((chin <= 14.0).sum())} — не выше 14 мм; "
          f"середина {np.median(chin):.2f} мм.")
    print(f"  Ширина лица: середина {np.median(width):.2f} мм, "
          f"разброс {width.min():.1f}…{width.max():.1f}.")
    tight = head <= 2.0
    if tight.any():
        print(f"\n  Где запаса меньше 2 мм ({int(tight.sum())} шт.) — там причёска "
              f"выше средней ({np.median(hair_h[tight]):.1f} против "
              f"{np.median(hair_h[~tight]):.1f} мм), а подбородок ниже "
              f"({np.median(chin[tight]):.1f} против "
              f"{np.median(chin[~tight]):.1f} мм): голову сдвинули вниз, "
              f"чтобы волосы влезли.")

    # Чем держится голова: запасом над волосами или подбородком.
    freedom = np.array([r["свобода сдвига, мм"] for r in rows])
    print(f"\n  Чем держится голова. Свобода сдвига — насколько подбородок "
          f"отличается от того, что получилось бы при постоянном запасе "
          f"{HEADROOM_MM:g} мм над волосами:")
    print(f"    середина {np.median(freedom):+.2f} мм, разброс "
          f"{freedom.min():+.2f}…{freedom.max():+.2f} мм, "
          f"размах {freedom.max() - freedom.min():.2f} мм")
    print(f"    связь свободы с высотой волос "
          f"{correlation(rows, 'свобода сдвига, мм', 'высота волос, мм'):+.2f}")
    print(f"    (около нуля — значит запас над волосами и есть правило; "
          f"устойчиво вниз при пышных волосах — значит правило держит подбородок, "
          f"а волосы тогда упираются в верх)")

    # Насколько программа ошибается сегодня: она ставит голову по оценке
    # макушки, то есть по подбородку и ширине лица.
    residual = np.array([r["волосы выше макушки, мм"] for r in rows])
    print(f"\n  Ошибка сегодняшней модели «макушка = подбородок + "
          f"{config.CROWN_RATIO_MEAN:g} × ширины лица» на этих же фотографиях:")
    print(f"    середина {np.median(residual):+.2f} мм, средний модуль "
          f"{np.abs(residual).mean():.2f} мм, разброс {residual.min():+.2f}…"
          f"{residual.max():+.2f} мм")
    print(f"    у {int((np.abs(residual) <= 2.0).sum())} из {len(rows)} ошибка "
          f"не больше 2 мм, у {int((np.abs(residual) <= 1.0).sum())} — не больше "
          f"1 мм, у {int((np.abs(residual) > 3.0).sum())} — больше 3 мм")
    compare_rules(rows, preset_height_mm())


def compare_rules(rows: list[dict], height_mm: float) -> None:
    """Какое правило постановки головы ближе к вашей практике.

    Проверяется не «как правило звучит», а насколько оно объясняет уже готовые
    фотографии: для каждой строки архива считаем, где оказался бы подбородок, и
    сравниваем с тем, где он есть. Правило, которое ближе к вашим рукам,
    и есть то, что стоит зашивать в программу.
    """
    chin = np.array([r["подбородок снизу, мм"] for r in rows])
    brow = np.array([r["бровь до подбородка, мм"] for r in rows])
    hair = np.array([r["высота волос, мм"] for r in rows])

    rules: dict[str, np.ndarray] = {
        f"подбородок всегда на {np.median(chin):.2f} мм "
        f"(то, как сейчас в ini)": np.full_like(chin, float(np.median(chin))),
        f"запас над волосами всегда {HEADROOM_MM:g} мм":
            height_mm - HEADROOM_MM - brow - hair,
    }
    for floor in (10.5, 11.5):
        rules[f"запас {HEADROOM_MM:g} мм, но подбородок не ниже {floor:g} мм"] = \
            np.maximum(height_mm - HEADROOM_MM - brow - hair, floor)

    print(f"\n  Какое правило ближе к вашим фотографиям (ошибка в подбородке, мм)")
    print(f"  {'правило':52s} {'середина':>9s} {'средний':>8s} {'худшая':>7s}")
    for name, predicted in rules.items():
        error = chin - predicted
        print(f"  {name:52s} {np.median(error):+9.2f} {np.abs(error).mean():8.2f} "
              f"{np.abs(error).max():7.2f}")


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else folder.parent / "тенденции.csv"
    if not folder.is_dir():
        print(f"Нет папки {folder}")
        return 1

    preset = config.apply_settings()[config.BASE_PRESET_ID]
    px_per_mm = preset["ppi"] / 25.4
    doc_h = round(preset["height_mm"] * px_per_mm)
    print(f"Папка {folder}")
    print(f"Кадр {round(preset['width_mm'] * px_per_mm)} × {doc_h} px, "
          f"{px_per_mm:.0f} px на мм, оценка макушки = "
          f"{config.CROWN_RATIO_MEAN:g} × ширины лица\n")

    files = sorted(folder.glob("*.jpg"))
    rows: list[dict] = []
    skipped: list[str] = []
    for i, path in enumerate(files, 1):
        row = analyse_photo(path, px_per_mm, doc_h)
        if row is None:
            skipped.append(path.name)
            continue
        rows.append(row)
        print(f"  {i:>3} из {len(files)}  {row['файл']}  "
              f"запас {row['запас над волосами, мм']:.2f} мм  "
              f"пышность {row['волосы выше макушки, мм']:+.2f} мм  "
              f"подбородок {row['подбородок снизу, мм']:.2f} мм", flush=True)

    if not rows:
        print("Лицо не нашлось ни на одной фотографии.")
        return 1

    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nРазобрано {len(rows)} из {len(files)}"
          + (f", без лица: {', '.join(skipped)}" if skipped else ""))
    print(f"Таблица: {out_path}")
    report(rows, folder)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
