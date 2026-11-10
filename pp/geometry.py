"""Расчёт трансформации фотографии на документ по требованиям МВД.

Порядок работы тот же, что и у вас вручную: сначала выравнивается наклон
головы, потом подбирается масштаб по ширине лица, потом голова ставится на
свои места — волосами на 3,1 мм от верхнего края кадра, лицо по центру боксов.
Подбородок при этом получается какой получится: так вы и делаете, и на архиве
из 81 готовой фотографии подбородок гуляет на ±2 мм, а запас над волосами
держится в пределах миллиметра.

Система координат — пиксели исходного изображения, ось Y вниз. Углы в градусах,
положительный угол — поворот по часовой стрелке на экране, как в Photoshop.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import config
from .face import Face, apply_similarity, estimate_norm

# ── Индексы 106 точек (InsightFace 2d106det) ───────────────────────────────
#
#   0        подбородок — нижняя центральная точка овала
#   1…32     овал лица; индексы перемешаны, порядок обхода в CONTOUR_LOOP
#   33…42    глаз слева в кадре (центр = 38)
#   43…51    бровь слева в кадре (верх = 49)
#   52…71    рот (углы = 52 и 61)
#   72…86    нос (переносица = 72, кончик = 86, под носом = 80)
#   87…96    глаз справа в кадре (центр = 88)
#   97…105   бровь справа в кадре (верх = 104)
#
# Овал НЕ замкнут на лбу: точек, перекрывающих лоб, в наборе нет. Это не мешает —
# ширина лица берётся по скулам, а высоту головы мы оцениваем антропометрически.
IDX = {
    "chin": 0,
    "eye_left": 38, "eye_right": 88,
    "mouth_left": 52, "mouth_right": 61,
    "brow_left": 49, "brow_right": 104,
    "nasion": 72, "nose_tip": 86,
    "contour_loop": [
        1, 9, 10, 11, 12, 13, 14, 15, 16, 2, 3, 4, 5, 6, 7, 8,
        0, 24, 23, 22, 21, 20, 19, 18, 32, 31, 30, 29, 28, 27, 26, 25, 17,
    ],
}


def norm180(deg: float) -> float:
    a = deg % 360.0
    if a > 180.0:
        a -= 360.0
    if a <= -180.0:
        a += 360.0
    return a


def weighted_median(values, weights) -> float:
    pairs = sorted(zip([norm180(v) for v in values], weights), key=lambda p: p[0])
    total = sum(p[1] for p in pairs)
    acc = 0.0
    for value, weight in pairs:
        acc += weight
        if acc >= total / 2:
            return value
    return pairs[-1][0]


# ── Выравнивание наклона ────────────────────────────────────────────────────


def contour_axis(lm: np.ndarray) -> float:
    """Главная ось овала лица (анализ главных компонент)."""
    pts = lm[IDX["contour_loop"]]
    c = pts.mean(axis=0)
    d = pts - c
    sxx = float((d[:, 0] ** 2).sum())
    syy = float((d[:, 1] ** 2).sum())
    sxy = float((d[:, 0] * d[:, 1]).sum())
    theta = 0.5 * np.arctan2(2 * sxy, sxx - syy)
    return norm180(float(np.degrees(theta)) - 90.0)


def tilt_signals(lm: np.ndarray) -> list[float]:
    """Независимые сигналы наклона в кропе. 0 = ровно."""
    def ang(a, b) -> float:
        return float(np.degrees(np.arctan2(b[1] - a[1], b[0] - a[0])))

    brow_mid = (lm[IDX["brow_left"]] + lm[IDX["brow_right"]]) / 2.0
    return [
        ang(lm[IDX["eye_left"]], lm[IDX["eye_right"]]),
        ang(lm[IDX["mouth_left"]], lm[IDX["mouth_right"]]),
        ang(lm[IDX["brow_left"]], lm[IDX["brow_right"]]),
        contour_axis(lm),
        norm180(ang(brow_mid, lm[IDX["chin"]]) + 90.0),
        norm180(ang(lm[IDX["nasion"]], lm[IDX["chin"]]) + 90.0),
    ]


def residual_tilt(crop_lm: np.ndarray, level_angles=None, weights=None) -> float:
    """Остаточный наклон лица в градусах: взвешенная медиана отклонений.

    Веса и уровни берутся из ini при каждом вызове — правка настроек не требует
    ни перезапуска Photoshop, ни чего-либо ещё.
    """
    level_angles = config.level_angles() if level_angles is None else level_angles
    weights = config.tilt_weights() if weights is None else weights
    signals = tilt_signals(crop_lm)
    residuals = [norm180(s - a) for s, a in zip(signals, level_angles)]
    return weighted_median(residuals, weights)


def to_crop_frame(lm106: np.ndarray, kps5: np.ndarray, crop_size: int = 192):
    """Перевод 106 точек в систему координат выровненного кропа.

    Ключевой приём: нормализация по 5 точкам уже доворачивает лицо, поэтому
    наклон, измеренный здесь, почти не содержит систематической ошибки — в
    отличие от угла линии глаз прямо в исходном кадре.
    """
    M = estimate_norm(kps5, crop_size)
    return apply_similarity(M, lm106), M


# ── Измерение лица ──────────────────────────────────────────────────────────
#
# Ни одна из этих величин не зависит от причёски: только подбородок, овал по
# скулам, глаза, рот и нос. Это ровно то, о чём вы просили.


@dataclass
class FaceMeasures:
    chin: np.ndarray
    cheek_left: np.ndarray
    cheek_right: np.ndarray
    face_width: float        # ширина лица по скулам
    oval_height: float       # овал: виски → подбородок
    chin_to_brow: float
    chin_to_eye: float
    nasion_to_chin: float
    eye_distance: float
    eye_mid: np.ndarray
    brow_mid: np.ndarray
    mouth_mid: np.ndarray
    nose_tip: np.ndarray
    nasion: np.ndarray
    center: np.ndarray       # центр овала: боковой центр по ширине скул
    top: float
    bottom: float


def measure_face(lm: np.ndarray) -> FaceMeasures:
    contour = lm[:33]
    i_left = int(np.argmin(contour[:, 0]))
    i_right = int(np.argmax(contour[:, 0]))
    top = float(contour[:, 1].min())
    bottom = float(contour[:, 1].max())
    eye_mid = (lm[IDX["eye_left"]] + lm[IDX["eye_right"]]) / 2.0
    brow_mid = (lm[IDX["brow_left"]] + lm[IDX["brow_right"]]) / 2.0
    return FaceMeasures(
        chin=lm[IDX["chin"]],
        cheek_left=contour[i_left],
        cheek_right=contour[i_right],
        face_width=float(np.linalg.norm(contour[i_left] - contour[i_right])),
        oval_height=bottom - top,
        chin_to_brow=float(np.linalg.norm(lm[IDX["chin"]] - brow_mid)),
        chin_to_eye=float(np.linalg.norm(lm[IDX["chin"]] - eye_mid)),
        nasion_to_chin=float(np.linalg.norm(lm[IDX["nasion"]] - lm[IDX["chin"]])),
        eye_distance=float(np.linalg.norm(lm[IDX["eye_left"]] - lm[IDX["eye_right"]])),
        eye_mid=eye_mid,
        brow_mid=brow_mid,
        mouth_mid=(lm[IDX["mouth_left"]] + lm[IDX["mouth_right"]]) / 2.0,
        nose_tip=lm[IDX["nose_tip"]],
        nasion=lm[IDX["nasion"]],
        center=np.array([(contour[i_left][0] + contour[i_right][0]) / 2.0,
                         (top + bottom) / 2.0]),
        top=top,
        bottom=bottom,
    )


def base_size() -> dict:
    """Размер кадра, к которому относятся нормы МВД из ini."""
    return config.apply_settings().get(config.BASE_PRESET_ID) or BASE_SIZE


def norm_band(preset: dict) -> dict:
    """Нормы МВД, пересчитанные пропорционально размеру кадра."""
    base = base_size()
    k_w = preset["width_mm"] / base["width_mm"]
    k_h = preset["height_mm"] / base["height_mm"]
    return {
        "width_min": config.get_float("mvd", "width_min_mm", 17.0) * k_w,
        "width_max": config.get_float("mvd", "width_max_mm", 21.0) * k_w,
        "height_min": config.get_float("mvd", "height_min_mm", 30.0) * k_h,
        "height_max": config.get_float("mvd", "height_max_mm", 33.0) * k_h,
    }


BASE_SIZE = {"width_mm": 37.0, "height_mm": 47.0}


# ── Круглая голова ──────────────────────────────────────────────────────────
#
# Лысину по точкам не видно: верхние точки овала — это виски, а не макушка.
# Поэтому круглоту приходится ловить косвенно, сразу по трём отношениям, и все
# три должны сработать — по одному признаку круглую голову не отличить:
#
#   овал / ширина лица            — у круглой головы высота близка к ширине
#   подбородок→глаза / ширина     — глаза низко, лицо «сплющено»
#   расстояние глаз / ширина       — у широкого круглого лица глаза отнесены
#                                    от краёв, то есть доля мала
#
# Третий признак — различающий. Без него круглым считается и худое узкое лицо:
# на ваших шести исходниках худой portrait (source5) по первым двум признакам
# «круглее» полного лысого (source1), и отличает его только третий — 0,444 против
# 0,414. Остальные лица отсекаются первыми двумя: 0,856…0,899 и 0,794…0,848.
#
# Пороги в ini подобраны по этим шести фотографиям. Один пример круглой головы —
# это всё же один пример: если поправка приходит не туда, её проще выставить
# вручную в окне выбора, а пороги подвинуть в ini.


@dataclass
class RoundFace:
    detected: bool
    oval_ratio: float
    chin_eye_ratio: float
    eye_ratio: float
    width_add_mm: float
    chin_up_mm: float
    mode: str


def detect_round_face(measures: FaceMeasures, mode: str = "auto",
                      settings: dict | None = None) -> RoundFace:
    """Круглая ли голова. mode: auto — по признакам, yes/no — как скажет оператор."""
    settings = settings or config.round_face_settings()
    width = measures.face_width or 1.0
    oval_ratio = measures.oval_height / width
    chin_eye_ratio = measures.chin_to_eye / width
    eye_ratio = measures.eye_distance / width
    if mode == "yes":
        detected = True
    elif mode == "no":
        detected = False
    else:
        detected = (settings["enable"]
                    and oval_ratio <= settings["oval_ratio_max"]
                    and chin_eye_ratio <= settings["chin_eye_ratio_max"]
                    and eye_ratio <= settings["eye_ratio_max"])
    return RoundFace(
        detected=detected,
        oval_ratio=oval_ratio,
        chin_eye_ratio=chin_eye_ratio,
        eye_ratio=eye_ratio,
        width_add_mm=settings["width_add_mm"] if detected else 0.0,
        chin_up_mm=settings["chin_up_mm"] if detected else 0.0,
        mode=mode,
    )


# ── Основной расчёт ─────────────────────────────────────────────────────────


@dataclass
class Transform:
    """Что и с какими числами делать со слоем в Photoshop."""
    rotate_deg: float
    scale: float
    translate: tuple[float, float]
    doc_width: int
    doc_height: int
    ppi: int
    pivot: tuple[float, float]
    source_size: tuple[int, int]
    report: dict = field(default_factory=dict)

    @property
    def target_center(self) -> tuple[float, float]:
        """Куда должен попасть центр слоя после поворота и масштаба.

        Photoshop двигает и поворачивает слои вокруг их центра, поэтому сдвиг
        удобнее считать как «центр слоя должен оказаться здесь».
        """
        return (self.pivot[0] + self.translate[0],
                self.pivot[1] + self.translate[1])


def solve_transform(face: Face, source_size: tuple[int, int], preset: dict,
                    round_face_mode: str = "auto") -> Transform:
    """Считает поворот, масштаб и сдвиг слоя.

    source_size — ширина и высота холста документа с фотографией (в пикселях).
    round_face_mode — «auto», «yes» или «no»: поправка для круглой головы.
    """
    src_w, src_h = source_size
    px_per_mm = preset["ppi"] / 25.4
    doc_w = round(preset["width_mm"] * px_per_mm)
    doc_h = round(preset["height_mm"] * px_per_mm)

    # 1. Наклон. Углы складываются: нормализация уже повернула исходник на
    #    M.rotDeg, а residual — то, что осталось в кропе. Значит доворот = минус сумма.
    crop_lm, M = to_crop_frame(face.lm106, face.kps5, 192)
    residual = residual_tilt(crop_lm)
    rot_M = float(np.degrees(np.arctan2(M[1], M[0])))
    rotate_deg = norm180(rot_M - residual)

    # Опорная точка — центр холста фотографии. Поворот и масштаб в Photoshop
    # делаются вокруг центра слоя, поэтому он остаётся на месте на обоих шагах
    # и пересчитывать его не нужно.
    pivot = (src_w / 2.0, src_h / 2.0)

    # 2. Масштаб — по ширине лица, точно по ширине боксов шаблона.
    #
    # Ширину меряем уже ПОСЛЕ поворота. У человека с развёрнутой в 3/4 головой
    # самая широкая точка овала лежит выше середины лица, и до поворота
    # горизонтальная проекция получается меньше настоящей ширины по скулам —
    # лицо уехало бы в кадр мельче нужного.
    lm_rot = rotate_points(face.lm106, rotate_deg, pivot)
    measures = measure_face(lm_rot)

    # 2б. Поправка на круглую голову: у полного круглолицого человека макушка
    #     по меркам программы оказывается ниже, чем нужно, и подбородок приходится
    #     опускать. Лечится тем, что лицо в кадре становится шире, а голова
    #     поднимается. Величины — в миллиметрах, в ini.
    round_face = detect_round_face(measures, round_face_mode)
    target_face_width_mm = preset["face_width_mm"] + round_face.width_add_mm
    target_chin_mm = preset["chin_from_bottom_mm"] + round_face.chin_up_mm

    target_face_width_px = target_face_width_mm * px_per_mm
    scale = target_face_width_px / measures.face_width

    # 3. Позиционирование.
    #
    # Поворот и масштаб в Photoshop делаются вокруг центра слоя, поэтому центр
    # C на обоих шагах остаётся на месте и его не нужно пересчитывать. Дальше
    # одним сдвигом ставим лицо на место: по X — центр овала лица на центр
    # боксов шаблона.
    #
    # По Y голову держит НЕ подбородок, а волосы: запас над ними в 3,1 мм —
    # то, что на самом деле делают руки. Проверено на архиве из 81 готовой
    # фотографии: правило «3,1 мм над волосами» объясняет положение подбородка
    # с ошибкой 0,29 мм, тогда как «подбородок всегда на 13,3 мм» — с ошибкой
    # 0,60 мм, и у девяти снимков расходится больше чем на 3 мм.
    #
    # У человека с пышной причёской волосы занимают место, где у другого
    # макушка, и держать 3,1 мм ради них — значит увести подбородок к самому
    # низу кадра. Поэтому есть нижняя граница (chin_floor_mm): подбородок не
    # опускается ниже неё, и место над волосами на единицы миллиметров
    # сжимается. В архиве подбородок опускается до 10,2 мм, и ниже не уходит.
    rad = np.radians(rotate_deg)
    cos, sin = float(np.cos(rad)), float(np.sin(rad))

    def place(point: np.ndarray) -> np.ndarray:
        dx = point[0] - pivot[0]
        dy = point[1] - pivot[1]
        return np.array([pivot[0] + scale * (cos * dx - sin * dy),
                         pivot[1] + scale * (sin * dx + cos * dy)])

    face_center_after = place(measures.center)
    chin_after = place(measures.chin)

    target_center_x = config.get_float("geometry", "face_center_x_frac", 0.5) * doc_w
    tx = target_center_x - face_center_after[0]

    headroom_px = preset["headroom_mm"] * px_per_mm
    chin_floor_px = preset["chin_floor_mm"] * px_per_mm
    target_chin_y = doc_h - target_chin_mm * px_per_mm

    hair_after = None
    if face.hair_top is not None:
        # Точку поворота для верха головы берём на вертикали глаз: голова стоит
        # над ними, и из-за наклона её собственная ширина тут ни при чём.
        hair_after = place(np.array([measures.eye_mid[0], face.hair_top]))

    if hair_after is not None:
        chin_limit_y = doc_h - chin_floor_px
        chin_ceiling_y = doc_h - preset["chin_ceiling_mm"] * px_per_mm
        ty = headroom_px - hair_after[1]
        floor_applied = chin_after[1] + ty > chin_limit_y
        ceiling_applied = chin_after[1] + ty < chin_ceiling_y
        if floor_applied:
            ty = chin_limit_y - chin_after[1]
        elif ceiling_applied:
            ty = chin_ceiling_y - chin_after[1]
    else:
        # Волосы не нашлись: остаётся прежнее правило по подбородку. Так программа
        # не встаёт враспорку на незнакомом фоне, просто считает по-старому.
        ty = target_chin_y - chin_after[1]
        floor_applied = False
        ceiling_applied = False

    chin_final_y = chin_after[1] + ty
    hair_final_y = None if hair_after is None else hair_after[1] + ty

    band = norm_band(preset)
    out_face_width_mm = measures.face_width * scale / px_per_mm
    out_crown_mm = out_face_width_mm * config.get_float(
        "geometry", "crown_ratio", 1.66)

    report = {
        "preset": preset["label"],
        "document": f"{doc_w} × {doc_h} px = "
                    f"{preset['width_mm']:g} × {preset['height_mm']:g} мм "
                    f"@ {preset['ppi']:g} ppi",
        "rotate_deg": round(rotate_deg, 3),
        "scale_percent": round(scale * 100, 2),
        "residual_tilt_deg": round(residual, 3),
        "eye_line_deg": round(tilt_signals(lm_rot)[0], 2),
        "face_width_mm": round(out_face_width_mm, 2),
        "crown_to_chin_mm": round(out_crown_mm, 2),
        "chin_from_bottom_mm": round((doc_h - chin_final_y) / px_per_mm, 2),
        "headroom_mm": None if hair_final_y is None
                        else round(hair_final_y / px_per_mm, 2),
        "headroom_target_mm": round(preset["headroom_mm"], 2),
        "hair_found": hair_after is not None,
        "chin_floor_applied": bool(floor_applied),
        "chin_floor_mm": round(preset["chin_floor_mm"], 2),
        "headroom_ceiling_applied": bool(ceiling_applied),
        "chin_ceiling_mm": round(preset["chin_ceiling_mm"], 2),
        "target_face_width_mm": round(target_face_width_mm, 2),
        "target_chin_from_bottom_mm": round(target_chin_mm, 2),
        "round_face": round_face.detected,
        "round_face_mode": round_face.mode,
        "round_face_oval_ratio": round(round_face.oval_ratio, 3),
        "round_face_chin_eye_ratio": round(round_face.chin_eye_ratio, 3),
        "round_face_eye_ratio": round(round_face.eye_ratio, 3),
        "round_face_add_mm": round(round_face.width_add_mm, 2),
        "round_face_up_mm": round(round_face.chin_up_mm, 2),
        "norm_width_mm": [round(band["width_min"], 1), round(band["width_max"], 1)],
        "norm_height_mm": [round(band["height_min"], 1), round(band["height_max"], 1)],
        "width_in_range": band["width_min"] <= out_face_width_mm <= band["width_max"],
        "crown_in_range": band["height_min"] <= out_crown_mm <= band["height_max"],
        "shift_px": [round(tx, 1), round(ty, 1)],
        "detection_score": round(face.score, 3),
    }
    return Transform(
        rotate_deg=rotate_deg,
        scale=scale,
        translate=(tx, ty),
        doc_width=doc_w,
        doc_height=doc_h,
        ppi=preset["ppi"],
        pivot=pivot,
        source_size=(src_w, src_h),
        report=report,
    )


def rotate_points(points: np.ndarray, deg: float, pivot: tuple[float, float]) -> np.ndarray:
    """Поворот точек вокруг точки на угол deg (по часовой стрелке на экране)."""
    rad = np.radians(deg)
    cos, sin = float(np.cos(rad)), float(np.sin(rad))
    points = np.asarray(points, dtype=np.float64)
    dx = points[:, 0] - pivot[0]
    dy = points[:, 1] - pivot[1]
    return np.stack([pivot[0] + cos * dx - sin * dy,
                     pivot[1] + sin * dx + cos * dy], axis=1)


def apply_transform(t: Transform, points: np.ndarray) -> np.ndarray:
    """Применяет трансформацию к точкам — для проверки и отладки."""
    rad = np.radians(t.rotate_deg)
    cos, sin = float(np.cos(rad)), float(np.sin(rad))
    points = np.asarray(points, dtype=np.float64)
    dx = points[:, 0] - t.pivot[0]
    dy = points[:, 1] - t.pivot[1]
    return np.stack([
        t.pivot[0] + t.scale * (cos * dx - sin * dy) + t.translate[0],
        t.pivot[1] + t.scale * (sin * dx + cos * dy) + t.translate[1],
    ], axis=1)