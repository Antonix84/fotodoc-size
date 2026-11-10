"""Разбор архива готовых фотографий.

    python tools\\analyse_archive.py [папка] [куда положить csv]

Прогоняет распознавание по всем снимкам в папке и собирает статистику: ширина
лица, положение подбородка, наклон, пропорции лица. По ней видно, что на самом
деле получается у живых людей — и какие значения задавать в passport.ini.

Архив — это уже готовые фотографии 1110 × 1410 px, то есть ровно 30 px на мм,
поэтому миллиметры считаются напрямую.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from pp import config, geometry
from pp.face import FaceNotFound, analyse_path

DEFAULT_DIR = config.samples_dir() / "learn" / "3,7x4,7"


def analyse_one(path: Path, px_per_mm: float, doc_h: int) -> dict | None:
    try:
        face, size = analyse_path(path)
    except (FaceNotFound, OSError):
        return None
    m = geometry.measure_face(face.lm106)
    crop_lm, M = geometry.to_crop_frame(face.lm106, face.kps5, 192)
    signals = geometry.tilt_signals(face.lm106)
    width = m.face_width
    return {
        "файл": path.name,
        "ширина лица, мм": round(width / px_per_mm, 2),
        "подбородок снизу, мм": round(doc_h / px_per_mm - m.chin[1] / px_per_mm, 2),
        "наклон глаз, °": round(geometry.norm180(signals[0]), 2),
        "наклон рта, °": round(geometry.norm180(signals[1]), 2),
        "наклон овала, °": round(geometry.norm180(signals[3]), 2),
        "овал/ширина": round(m.oval_height / width, 3),
        "подб-глаза/ширина": round(m.chin_to_eye / width, 3),
        "глаза/ширина": round(m.eye_distance / width, 3),
        "подб-брови/ширина": round(m.chin_to_brow / width, 3),
        "уверенность": round(face.score, 3),
    }


def describe(rows: list[dict], key: str) -> str:
    values = np.array([r[key] for r in rows], dtype=float)
    return (f"{values.min():7.3f} … {values.max():7.3f}   "
            f"среднее {values.mean():7.3f}   середина {np.median(values):7.3f}")


def drift(rows: list[dict], folder: Path, preset: dict, mode: str) -> None:
    """Куда программа сдвинула бы каждую фотографию архива.

    Фотографии из архива уже готовые, то есть сделанные руками или прежней
    версией программы. Расхождение с расчётом показывает, насколько её
    собственная математика совпадает с вашей практикой.

    Сравнивается не целевое значение из ini, а то, что программа реально
    поставит: положение головы теперь задают волосы, а не подбородок.
    """
    from pp.face import analyse_path as _analyse

    px_per_mm = preset["ppi"] / 25.4
    moves: list[tuple[float, float, float, float | None]] = []
    for row in rows:
        face, size = _analyse(folder / row["файл"])
        transform = geometry.solve_transform(face, size, preset, mode)
        moves.append((
            transform.report["face_width_mm"] - row["ширина лица, мм"],
            transform.report["chin_from_bottom_mm"] - row["подбородок снизу, мм"],
            transform.report["rotate_deg"],
            transform.report["headroom_mm"],
        ))
    values = np.array([m[:3] for m in moves])
    print()
    print("  Куда программа сдвинула бы эти готовые фотографии")
    print("  ----------------------------------------------------------")
    print(f"  по ширине лица    {values[:, 0].min():+.2f} … "
          f"{values[:, 0].max():+.2f} мм, середина {np.median(values[:, 0]):+.2f} мм")
    print(f"  по подбородку     {values[:, 1].min():+.2f} … "
          f"{values[:, 1].max():+.2f} мм, середина {np.median(values[:, 1]):+.2f} мм")
    print(f"  поворот           {values[:, 2].min():+.2f} … "
          f"{values[:, 2].max():+.2f}°, середина {np.median(values[:, 2]):+.2f}°")
    head = np.array([m[3] for m in moves if m[3] is not None])
    if head.size:
        print(f"  запас над волосами {head.min():.2f} … {head.max():.2f} мм, "
              f"середина {np.median(head):.2f} "
              f"(задано {preset['headroom_mm']:.2f} мм, "
              f"пол подбородка {preset['chin_floor_mm']:.2f} мм)")
    print("  (много — значит программа и ваши ручные результаты спорят)")


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else folder.parent / "разбор.csv"
    if not folder.is_dir():
        print(f"Нет папки {folder}")
        return 1

    preset = config.apply_settings()[config.BASE_PRESET_ID]
    px_per_mm = preset["ppi"] / 25.4
    doc_h = round(preset["height_mm"] * px_per_mm)
    print(f"Папка {folder}")
    print(f"Размер кадра {round(preset['width_mm'] * px_per_mm)} × {doc_h} px, "
          f"{px_per_mm:.0f} px на мм\n")

    files = sorted(folder.glob("*.jpg"))
    rows: list[dict] = []
    skipped: list[str] = []
    for i, path in enumerate(files, 1):
        row = analyse_one(path, px_per_mm, doc_h)
        if row is None:
            skipped.append(path.name)
            continue
        rows.append(row)
        print(f"  {i:>3} из {len(files)}  {row['файл']}  "
              f"{row['ширина лица, мм']:.2f} мм  "
              f"{row['подбородок снизу, мм']:.2f} мм  "
              f"{row['наклон глаз, °']:+.2f}°", flush=True)

    if not rows:
        print("Лицо не нашлось ни на одной фотографии.")
        return 1

    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nРазобрано {len(rows)} из {len(files)}"
          + (f", без лица: {', '.join(skipped)}" if skipped else ""))
    print(f"Таблица: {out_path}\n")
    print("  величина                 разброс              среднее   середина")
    print("  ------------------------ -------------------- --------- ---------")
    for key in rows[0]:
        if key == "файл":
            continue
        print(f"  {key:24s} {describe(rows, key)}")

    settings = config.round_face_settings()
    round_like = [r for r in rows
                  if r["овал/ширина"] <= settings["oval_ratio_max"]
                  and r["подб-глаза/ширина"] <= settings["chin_eye_ratio_max"]
                  and r["глаза/ширина"] <= settings["eye_ratio_max"]]
    print()
    print(f"  под поправку на круглую голову попадают {len(round_like)} из "
          f"{len(rows)}: {', '.join(r['файл'][:-4] for r in round_like)}")

    drift(rows, folder, preset, config.get("round_face", "mode", "auto"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())