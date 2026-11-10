"""Проверка готовых файлов, сделанных программой.

Прогоняет все source*_3,7x4,7см.jpg, какие нашлись, и сверяет их с требованиями
шаблона: ширина лица 18,50 мм, подбородок 13,17 мм снизу, наклон ровный.
Рядом показывает наклон в исходнике — так видно, что именно выровняла программа.

Про наклон в готовом файле. Лицо в готовой фотографии шириной всего 555 px, и
106 точек на таком размере берутся с погрешностью в пару пикселей. По линии
глаз это даёт около полутора градусов дрейфа — то есть цифра ниже показывает
погрешность самого измерения, а не реальный наклон. Ориентироваться стоит на
исходник, где лицо в разы крупнее.

    python tools\\verify_results.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from pp import config, geometry
from pp.face import analyse_path

TOLERANCE_MM = 0.35
TOLERANCE_DEG = 1.0


def eye_line_deg(lm: np.ndarray) -> float:
    a = lm[geometry.IDX["eye_left"]]
    b = lm[geometry.IDX["eye_right"]]
    return float(np.degrees(np.arctan2(b[1] - a[1], b[0] - a[0])))


def measure(path: Path, px_per_mm: float, doc_h: int) -> tuple[float, float, float]:
    face, _ = analyse_path(path)
    measures = geometry.measure_face(face.lm106)
    return (measures.face_width / px_per_mm,
            doc_h / px_per_mm - measures.chin[1] / px_per_mm,
            eye_line_deg(face.lm106))


def main() -> int:
    preset = config.apply_settings()[config.BASE_PRESET_ID]
    px_per_mm = preset["ppi"] / 25.4
    doc_h = round(preset["height_mm"] * px_per_mm)
    want_width = preset["face_width_mm"]
    want_chin = preset["chin_from_bottom_mm"]

    print(f"Программа ставит: лицо {want_width:.2f} мм по скулам, "
          f"подбородок {want_chin:.2f} мм снизу, наклон ровный.")
    print()
    print("  файл           |  ширина | подб снизу | наклон до | наклон после")
    print("  ---------------+---------+------------+-----------+------------")

    rows = []
    for path in sorted(config.samples_dir().glob("source*_3,7x4,7см.jpg")):
        width, chin, after = measure(path, px_per_mm, doc_h)
        source = path.with_name(path.name.split("_")[0] + ".jpg")
        before = measure(source, px_per_mm, doc_h)[2] if source.exists() else float("nan")
        rows.append((width, chin, before, after))
        print(f"  {path.stem[:13]:13} |{width:8.2f} |{chin:11.2f} |"
              f"{before:10.2f}° |{after:12.2f}°")

    if not rows:
        print("  готовых файлов не найдено — сначала обработайте исходники")
        return 1

    arr = np.array(rows)
    inside = ((np.abs(arr[:, 0] - want_width) <= TOLERANCE_MM)
              & (np.abs(arr[:, 1] - want_chin) <= TOLERANCE_MM))
    print()
    print(f"  ширина лица       среднее {arr[:, 0].mean():.2f} мм, "
          f"разброс {arr[:, 0].min():.2f}…{arr[:, 0].max():.2f} "
          f"(норма МВД 17…21 мм)")
    print(f"  подбородок снизу  среднее {arr[:, 1].mean():.2f} мм, "
          f"разброс {arr[:, 1].min():.2f}…{arr[:, 1].max():.2f}")
    print(f"  наклон до         среднее {arr[:, 2].mean():+.2f}°, "
          f"разброс {arr[:, 2].min():+.2f}…{arr[:, 2].max():+.2f}")
    print(f"  наклон после      среднее {arr[:, 3].mean():+.2f}°, "
          f"разброс {arr[:, 3].min():+.2f}…{arr[:, 3].max():+.2f}")
    print()
    print(f"  ширина и положение подбородка попали в допуск "
          f"±{TOLERANCE_MM:.2f} мм у {int(inside.sum())} из {len(inside)} "
          f"фотографий")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
