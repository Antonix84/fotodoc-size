# Сторонние компоненты

## InsightFace buffalo_l

Программа использует две модели распознавания лиц из набора
[InsightFace](https://github.com/deepinsight/insightface) `buffalo_l`:

| Файл | Назначение |
|---|---|
| `models/det_10g.onnx` | детектор лиц SCRFD |
| `models/2d106det.onnx` | разметка 106 точек лица |

- Код InsightFace распространяется по лицензии Apache-2.0.
- Веса моделей распространяются по лицензии
  [CC-BY-NC-4.0](https://creativecommons.org/licenses/by-nc/4.0/): только
  некоммерческое использование, с указанием авторства. Веса нельзя продавать
  как отдельный продукт. Использование для обычной печати фотографий на
  документы допускается.
- Официальный источник: <https://github.com/deepinsight/insightface>

## onnxruntime

© Microsoft Corporation, лицензия MIT.
<https://github.com/microsoft/onnxruntime>

## NumPy

© NumPy Developers, лицензия BSD-3-Clause.
<https://numpy.org>

## Pillow

© Python Imaging Library (PIL) contributors, лицензия MIT-CMU.
<https://python-pillow.org>

## pywin32

© Mark Hammond и contributors, лицензия PSF-2.0.
<https://github.com/mhammond/pywin32>
