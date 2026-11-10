"""Распознавание лица: SCRFD + 106 точек на моделях InsightFace (buffalo_l).

Два этапа, оба на onnxruntime:
  1) det_10g.onnx  — детектор SCRFD: находит лицо и даёт 5 опорных точек
  2) 2d106det.onnx — регрессия 106 точек по выровненному кропу 192×192

Обе модели уже лежат в models/, ничего скачивать не нужно.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np
import onnxruntime as ort
from PIL import Image

from . import config

DET_SIZE = 640
DET_STRIDES = (8, 16, 32)
DET_NUM_ANCHORS = 2
DET_MEAN = 127.5
DET_STD = 128.0
LM_SIZE = 192

# 2d106det экспортирован из MXNet и ждёт сырые значения 0…255 без нормализации.
# Это легко спутать со стандартным (v − 127.5) / 128, и тогда точки сбиваются
# в центр лица. Проверено на шести ваших примерах.
LM_MEAN = 0.0
LM_STD = 1.0

# Опорный шаблон ArcFace для 5 точек (база 112×112) — по нему делается
# нормализация лица в квадрат, как в InsightFace norm_crop.
TPL5_112 = np.array([
    [38.2946, 51.6963],   # левый глаз
    [73.5318, 51.5014],   # правый глаз
    [56.0252, 71.7366],   # нос
    [41.5493, 92.3655],   # левый угол рта
    [70.7299, 92.2041],   # правый угол рта
], dtype=np.float64)

_sessions: dict[str, ort.InferenceSession] = {}
_lock = threading.Lock()


def get_sessions() -> dict[str, ort.InferenceSession]:
    with _lock:
        if not _sessions:
            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            # Пути к моделям берём при загрузке, а не при импорте: ini читается
            # позже, если его кто-то поправил в первый запуск.
            models = config.models_dir()
            _sessions["det"] = ort.InferenceSession(
                str(models / "det_10g.onnx"), opts,
                providers=["CPUExecutionProvider"])
            _sessions["lm"] = ort.InferenceSession(
                str(models / "2d106det.onnx"), opts,
                providers=["CPUExecutionProvider"])
        return _sessions


@dataclass
class Face:
    score: float
    bbox: np.ndarray        # x0, y0, x1, y1
    kps5: np.ndarray        # 5 точек SCRFD
    lm106: np.ndarray       # 106 точек, координаты исходного изображения
    size: tuple[int, int] = (0, 0)   # размер исходного изображения, px
    # Верх головы вместе с волосами в пикселях исходника. None — определить не
    # удалось: волосы уходят за край кадра или фон не отделился от головы.
    # По архиву готовых фотографий (81 снимок) вы держите 3,1 мм над волосами, и
    # держите независимо от подбородка, поэтому эта точка нужнее оценки макушки.
    hair_top: float | None = None


# ── Верх головы ──────────────────────────────────────────────────────────────
#
# В 106 точках макушки нет, поэтому до недавнего времени верх головы оценивался
# арифметически: подбородок вверх на 1,66 × ширины лица. На архиве из 81
# готовой фотографии эта оценка в среднем права (−0,06 мм), но разбегается на
# ±5 мм — и вся разница приходится на причёску: у пышных волос макушка выше
# оценки, у гладко зачёсанных и у лысых — ниже.
#
# Поэтому верх головы измеряется по картинке. Метод простой и намеренно
# локальный: фон берётся ПОСТРОЧНО по бокам полосы над лицом, а «волосами»
# считается строка, в которой середина полосы отличается от этого фона. Так не
# важны ни цвет подложки, ни её перепад сверху вниз, ни то, что фон вообще
# не однотонный.

# Насколько шире лица берётся полоса поиска: пышная причёска шире головы.
BAND_FACE_WIDTHS = 1.15
# Доля половины полосы, занятая фоном по бокам.
BAND_SIDE = 0.18
# Доля центральной части полосы, которая должна отличаться от фона. Подобрана
# по архиву готовых фотографий: при 0,08 детектор совпадает с запасом над
# волосами, посчитанным «по всей ширине кадра», в пределах 0,15 мм. При 0,35 он
# пропускает тонкие пряди над основной массой волос и ошибается на 1,4 мм.
BAND_FILL = 0.08
# Насколько строка должна отличаться от фона по яркости (0…255).
BAND_DIFF = 26
# Сколько строк ниже найденной должно продолжаться «головное», чтобы отсечь
# одиночные вкрапления: край штор, блик, прядь в стороне.
BAND_HOLD_FACE_WIDTHS = 0.30
BAND_HOLD_FILL = 0.6
# Выше этой высоты над бровями голова не бывает: значит поймали что-то в фоне.
BAND_MAX_FACE_WIDTHS = 2.2


def _head_band(img: np.ndarray, eye_x: float, face_width: float,
               brow_y: float) -> tuple[int, int, int, int] | None:
    """Полоса над лицом: (x0, x1, y0, y1) в пикселях. None — полоса не помещается.

    Полоса шире лица, и на готовом паспортном кадре она за края не помещается —
    поэтому обрезается по границам изображения, а не отбрасывается. Если после
    обрезки полоса слишком узкая, фона по бокам уже не набрать и возвращается
    None: тогда детектор честно скажет «не знаю», и программа посчитает иначе.
    """
    height, width = img.shape[:2]
    half = BAND_FACE_WIDTHS * face_width
    x0 = max(0, int(round(eye_x - half)))
    x1 = min(width, int(round(eye_x + half)))
    if x1 - x0 < max(8, 0.3 * face_width):
        return None
    y1 = int(round(brow_y))
    if y1 <= 2:
        return None
    return x0, x1, 0, y1


def hair_top_px(img: np.ndarray, lm106: np.ndarray, eye_x: float) -> float | None:
    """Верх головы с волосами в пикселях того же изображения.

    None, если мерить нечего: полоса не помещается в кадр, волосы уходят за
    верхний край или фон не отделяется от головы нигде над бровями.
    """
    contour = lm106[:33]
    face_width = float(np.linalg.norm(contour[np.argmin(contour[:, 0])]
                                       - contour[np.argmax(contour[:, 0])]))
    brow_y = float(lm106[49][1] + lm106[104][1]) / 2.0     # брови: 49 и 104
    band = _head_band(img, eye_x, face_width, brow_y)
    if band is None:
        return None
    x0, x1, y0, y1 = band
    side = max(1, int((x1 - x0) * BAND_SIDE / 2))
    core = np.arange(x0 + side, x1 - side)
    if core.size < 4:
        return None

    strip = img[y0:y1, x0:x1].astype(np.int16)
    edges = np.concatenate([strip[:, :side], strip[:, -side:]], axis=1)
    background = np.median(edges, axis=1)                  # фон своей строки
    middle = strip[:, side:strip.shape[1] - side]
    differs = np.abs(middle - background[:, None, :]).max(axis=2) > BAND_DIFF
    filled = differs.mean(axis=1) >= BAND_FILL
    rows = np.nonzero(filled)[0]
    if rows.size == 0:
        return None

    hold = max(2, int(BAND_HOLD_FACE_WIDTHS * face_width))
    for row in rows:
        # Волосы у самой кромки кадра обрезаны: сколько над ними места — неизвестно.
        if row == 0:
            return None
        below = filled[row:row + hold]
        if below.size and below.mean() >= BAND_HOLD_FILL:
            if brow_y - (y0 + row) > BAND_MAX_FACE_WIDTHS * face_width:
                return None     # слишком высоко: это что-то в фоне, а не голова
            return float(y0 + row)
    return None


def similarity(src: np.ndarray, dst: np.ndarray) -> tuple[float, float, float, float]:
    """Преобразование подобия (поворот + масштаб + сдвиг) по парам точек.

    Возвращает (a, b, c, d):  x' = a·x − b·y + c,  y' = b·x + a·y + d.
    """
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    ms = src.mean(axis=0)
    md = dst.mean(axis=0)
    s = src - ms
    d = dst - md
    ra = float((s * d).sum())
    rb = float((s[:, 0] * d[:, 1] - s[:, 1] * d[:, 0]).sum())
    den = float((s * s).sum())
    a = ra / den
    b = rb / den
    c = md[0] - (a * ms[0] - b * ms[1])
    dd = md[1] - (b * ms[0] + a * ms[1])
    return a, b, c, dd


def apply_similarity(m: tuple[float, float, float, float],
                     points: np.ndarray) -> np.ndarray:
    a, b, c, d = m
    points = np.asarray(points, dtype=np.float64)
    return np.stack([a * points[:, 0] - b * points[:, 1] + c,
                     b * points[:, 0] + a * points[:, 1] + d], axis=1)


def apply_inverse_similarity(m: tuple[float, float, float, float],
                             points: np.ndarray) -> np.ndarray:
    """Обратное преобразование: из координат кропа обратно в исходник."""
    a, b, c, d = m
    points = np.asarray(points, dtype=np.float64)
    dx = points[:, 0] - c
    dy = points[:, 1] - d
    det = a * a + b * b
    return np.stack([(a * dx + b * dy) / det, (a * dy - b * dx) / det], axis=1)


def estimate_norm(kps5: np.ndarray, out_size: int = LM_SIZE) -> tuple[float, float, float, float]:
    tpl = TPL5_112 * (out_size / 112.0)
    return similarity(kps5, tpl)


def load_image(path) -> np.ndarray:
    """RGB uint8. Сторону ограничиваем DETECT_MAX_SIDE — точки от этого не страдают."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        limit = config.get_int("general", "detect_max_side", 2000)
        if max(im.size) > limit:
            scale = limit / max(im.size)
            im = im.resize((max(1, round(im.width * scale)),
                            max(1, round(im.height * scale))),
                           Image.LANCZOS)
        return np.asarray(im, dtype=np.uint8)


def _sample_rect(img: np.ndarray, x0: float, y0: float, x1: float, y1: float,
                 out_w: int, out_h: int, mean: float, std: float) -> np.ndarray:
    """Билинейная выборка прямоугольника в NCHW float32."""
    h, w = img.shape[:2]
    rw = max(1e-6, x1 - x0)
    rh = max(1e-6, y1 - y0)
    xs = x0 + (np.arange(out_w) + 0.5) * rw / out_w - 0.5
    ys = y0 + (np.arange(out_h) + 0.5) * rh / out_h - 0.5
    xi = np.clip(np.rint(xs), 0, w - 1).astype(np.int64)
    yi = np.clip(np.rint(ys), 0, h - 1).astype(np.int64)
    patch = img[np.ix_(yi, xi)].astype(np.float32)  # out_h, out_w, 3
    patch = (patch - mean) / std
    return np.ascontiguousarray(patch.transpose(2, 0, 1)[None])


def _nms(dets: np.ndarray, threshold: float) -> list[int]:
    order = np.argsort(-dets[:, 4])
    areas = (dets[:, 2] - dets[:, 0]) * (dets[:, 3] - dets[:, 1])
    keep: list[int] = []
    dead = np.zeros(len(dets), dtype=bool)
    for i in order:
        if dead[i]:
            continue
        keep.append(int(i))
        w = np.maximum(0.0, np.minimum(dets[i, 2], dets[:, 2]) - np.maximum(dets[i, 0], dets[:, 0]))
        h = np.maximum(0.0, np.minimum(dets[i, 3], dets[:, 3]) - np.maximum(dets[i, 1], dets[:, 1]))
        inter = w * h
        iou = inter / np.maximum(1e-9, areas[i] + areas - inter)
        dead |= iou > threshold
    return keep


def detect(img: np.ndarray, threshold: float | None = None) -> list[dict]:
    """Детекция лиц. Возвращает список, отсортированный по убыванию уверенности."""
    thr = config.get_float("general", "face_detect_threshold", 0.4) \
        if threshold is None else threshold
    sess = get_sessions()["det"]
    height, width = img.shape[:2]
    scale = min(DET_SIZE / width, DET_SIZE / height)
    # Вписываем изображение в верхний левый угол квадрата, остальное — нулями.
    # Именно так делает insightface: image_size фиксирован, паддинг справа/снизу.
    side = DET_SIZE / scale
    tensor = _sample_rect(img, 0, 0, side, side, DET_SIZE, DET_SIZE, DET_MEAN, DET_STD)

    input_name = sess.get_inputs()[0].name
    outputs = sess.run(None, {input_name: tensor})

    dets: list[np.ndarray] = []
    det_kps: list[np.ndarray] = []
    det_score: list[float] = []
    for lv, stride in enumerate(DET_STRIDES):
        scores = outputs[lv].reshape(-1)
        bbox = outputs[lv + 3].reshape(-1, 4)
        kps = outputs[lv + 6].reshape(-1, 10)
        f = DET_SIZE / stride
        anchor = np.nonzero(scores >= thr)[0]
        if anchor.size == 0:
            continue
        ko = anchor // DET_NUM_ANCHORS
        x = ko % f
        y = ko // f
        cx = x * stride
        cy = y * stride
        dets.append(np.stack([
            cx - bbox[anchor, 0] * stride,
            cy - bbox[anchor, 1] * stride,
            cx + bbox[anchor, 2] * stride,
            cy + bbox[anchor, 3] * stride,
        ], axis=1))
        k = kps[anchor].reshape(-1, 5, 2)
        det_kps.append(np.stack([cx[:, None] + k[:, :, 0] * stride,
                                 cy[:, None] + k[:, :, 1] * stride], axis=2))
        det_score.append(scores[anchor])

    if not dets:
        return []
    dets_arr = np.concatenate(dets, axis=0)
    kps_arr = np.concatenate(det_kps, axis=0)
    score_arr = np.concatenate(det_score, axis=0)
    keep = _nms(np.concatenate([dets_arr, score_arr[:, None]], axis=1), 0.4)
    faces = [
        {"score": float(score_arr[i]), "bbox": dets_arr[i] / scale,
         "kps": kps_arr[i] / scale}
        for i in keep
    ]
    faces.sort(key=lambda f: -f["score"])
    return faces


def landmark106(img: np.ndarray, kps5: np.ndarray,
                out_size: int = LM_SIZE) -> np.ndarray:
    """106 точек лица в пикселях исходного изображения."""
    sess = get_sessions()["lm"]
    height, width = img.shape[:2]
    M = estimate_norm(kps5, out_size)
    a, b, tx, ty = M
    det = a * a + b * b

    half = out_size / 2.0
    coords = np.arange(out_size) + 0.5
    dx = coords[None, :] - tx                  # out_w по X
    dy = (coords - ty)[:, None]                 # out_h по Y
    u = (a * dx + b * dy) / det
    v = (a * dy - b * dx) / det

    inside = (u >= 0) & (u <= width - 1) & (v >= 0) & (v <= height - 1)
    ui = np.clip(np.rint(u), 0, width - 1).astype(np.int64)
    vi = np.clip(np.rint(v), 0, height - 1).astype(np.int64)
    patch = img[vi, ui].astype(np.float32)          # out_h, out_w, 3
    patch[~inside] = 0.0
    patch = (patch - LM_MEAN) / LM_STD
    tensor = np.ascontiguousarray(patch.transpose(2, 0, 1)[None])

    input_name = sess.get_inputs()[0].name
    pts = sess.run(None, {input_name: tensor})[0].reshape(-1, 2)[:106]
    # модель отдаёт координаты в [-1,1]; переводим в пиксели кропа…
    crop_pts = (pts + 1.0) * half
    # …и обратно в пиксели исходника тем же обратным преобразованием
    return apply_inverse_similarity(M, crop_pts)


def analyse(img: np.ndarray) -> Face:
    """Полный конвейер для одного изображения. Бросает исключение, если лица нет."""
    faces = detect(img)
    if not faces:
        raise FaceNotFound("Лицо не найдено в кадре")
    # При нескольких лицах берём самое крупное: для студийного портрета это
    # заведомо нужное, а «самое уверенное» иногда уходит на лицо на заднем плане.
    face = max(faces, key=lambda f: (f["bbox"][2] - f["bbox"][0]) * (f["bbox"][3] - f["bbox"][1]))
    lm = landmark106(img, face["kps"])
    return Face(score=face["score"], bbox=face["bbox"], kps5=face["kps"], lm106=lm)


class FaceNotFound(RuntimeError):
    """В кадре не нашлось лица, на которое можно опереться."""


def analyse_path(path) -> tuple[Face, tuple[int, int]]:
    """Распознаёт лицо в файле.

    Точки возвращаются в координатах ИСХОДНОГО изображения, а не того уменьшенного
    кадра, на котором шло распознавание. Это важно: слой в Photoshop имеет
    полный размер, и сдвиг считается от его центра — смешивать тут два
    масштаба нельзя.
    """
    with Image.open(path) as im:
        original = im.size
    img = load_image(path)
    face = analyse(img)
    # Верх головы меряем на том же уменьшенном кадре, на котором шло узнавание,
    # и только потом переводим в пиксели оригинала — вместе с точками лица.
    face.hair_top = hair_top_px(img, face.lm106, float(face.kps5[:2, 0].mean()))
    factor = original[0] / img.shape[1]
    if face.hair_top is not None:
        face.hair_top *= factor
    face.lm106 = face.lm106 * factor
    face.bbox = face.bbox * factor
    face.kps5 = face.kps5 * factor
    face.size = original
    return face, original