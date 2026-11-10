"""Проверка без Photoshop: прогоняет ваши шесть пар source → result.

Показывает, что делает программа на исходниках, и рядом — что получилось
у вас вручную. Ничего не меняет, файлы не трогает.

    python tools\\verify_python.py            режим из ini
    python tools\\verify_python.py no         без поправки на круглую голову
    python tools\\verify_python.py yes        поправка всегда
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from pp import config, geometry
from pp.face import analyse_path

PX_PER_MM = config.PX_PER_MM


def eye_line_deg(lm: np.ndarray) -> float:
    a = lm[geometry.IDX["eye_left"]]
    b = lm[geometry.IDX["eye_right"]]
    return float(np.degrees(np.arctan2(b[1] - a[1], b[0] - a[0])))


def measure(path: Path):
    """Замеры прямо в готовом файле, без всякой трансформации."""
    face, _ = analyse_path(path)
    return geometry.measure_face(face.lm106), face


def fmt_manual(path: Path, doc_h: int) -> str:
    """Ваш результат, как есть: ширина лица, подбородок снизу, наклон глаз."""
    if not path.exists():
        return "нет файла"
    m, face = measure(path)
    return (f"{m.face_width / PX_PER_MM:5.2f} мм / "
            f"{doc_h / PX_PER_MM - m.chin[1] / PX_PER_MM:5.2f} мм / "
            f"{eye_line_deg(face.lm106):+.2f}°")


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else config.get(
        "round_face", "mode", "auto")
    if mode not in ("auto", "yes", "no"):
        mode = "auto"

    preset = config.apply_settings()[config.BASE_PRESET_ID]
    samples = config.samples_dir()
    doc_h = round(preset["height_mm"] * PX_PER_MM)
    want_width = preset["face_width_mm"]
    want_chin = preset["chin_from_bottom_mm"]
    want_centre = config.get_float("geometry", "face_center_x_frac", 0.4977) \
        * preset["width_mm"]
    settings = config.round_face_settings()

    print(f"Размер {preset['label']}, режим головы: {mode}")
    print(f"Программа кладёт: ширина лица {want_width:.2f} мм, подбородок "
          f"{want_chin:.2f} мм снизу, центр лица {want_centre:.2f} мм, "
          f"наклон 0.00°")
    if settings["enable"] and mode != "no":
        print(f"Круглая голова, если овал/ширина ≤ {settings['oval_ratio_max']}, "
              f"подбородок-глаза/ширина ≤ {settings['chin_eye_ratio_max']} и "
              f"глаза/ширина ≤ {settings['eye_ratio_max']} → "
              f"+{settings['width_add_mm']:g} мм по ширине, "
              f"+{settings['chin_up_mm']:g} мм вверх")
    print()
    print("  пара | моя ширина | моя поза | подб снизу | центр X | наклон глаз | "
          "макушка→подб | овал/подб-глаза/глаза || вручную: ширина / подб / наклон")
    print("  -----+------------+----------+-----------+---------+-------------+"
          "-------------+---------+---------------------------")

    mine = []
    for n in range(1, 50):
        src = samples / f"source{n}.jpg"
        res = samples / f"result{n}.jpg"
        if not src.exists():
            break

        face, size = analyse_path(src)
        t = geometry.solve_transform(face, size, preset, mode)
        out_lm = geometry.apply_transform(t, face.lm106)
        out = geometry.measure_face(out_lm)

        width = out.face_width / PX_PER_MM
        chin = doc_h / PX_PER_MM - out.chin[1] / PX_PER_MM
        centre = out.center[0] / PX_PER_MM
        tilt = eye_line_deg(out_lm)
        mine.append((width, chin, centre, tilt))

        print(f"  {n:>4} |{width:11.2f} мм |{chin:8.2f} мм |{centre:9.2f} |"
              f"{tilt:9.2f}° |{t.report['crown_to_chin_mm']:8.2f} мм |"
              f"{t.report['round_face_oval_ratio']:.3f}/"
              f"{t.report['round_face_chin_eye_ratio']:.3f}/"
              f"{t.report['round_face_eye_ratio']:.3f}"
              f"{'  круглая' if t.report['round_face'] else ''} || "
              f"{fmt_manual(res, doc_h)}")

    if not mine:
        print(f"  пары source*/result* не найдены в папке {samples}")
        return 1

    arr = np.array(mine)
    print()
    print(f"  ширина лица      среднее {arr[:, 0].mean():.2f} мм, "
          f"разброс {arr[:, 0].min():.2f}…{arr[:, 0].max():.2f} "
          f"(надо ровно {want_width:.2f})")
    print(f"  подбородок снизу среднее {arr[:, 1].mean():.2f} мм "
          f"(надо ровно {want_chin:.2f})")
    print(f"  центр лица по X  среднее {arr[:, 2].mean():.2f} мм "
          f"(надо ровно {want_centre:.2f})")
    print(f"  наклон линии глаз среднее {arr[:, 3].mean():+.3f}°, "
          f"разброс {arr[:, 3].min():+.3f}…{arr[:, 3].max():+.3f} (надо 0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())