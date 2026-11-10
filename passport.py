"""Программа «Фото на документ по требованиям МВД».

Её запускает скрипт Photoshop passport-photo.jsx — по горячей клавише.
Дальше так:

  1. Photoshop выгружает копию открытой фотографии во временный PSD.
  2. Здесь мы показываем окно выбора размера и ждём вашего решения.
  3. Находим лицо, строим 106 точек, выравниваем наклон по овалу лица.
  4. Считаем масштаб по ширине лица и ставим голову на направляющие шаблона.
  5. Отдаём Photoshop числа — он собирает результат в шаблоне.
  6. Сверяем готовый файл тем же распознаванием и показываем отчёт.

Все настройки — в passport.ini рядом с программой. Собранный exe запускается
на любом компьютере: python в системе не нужен.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pp import bridge, config, geometry, installer  # noqa: E402
from pp.face import FaceNotFound, analyse_path  # noqa: E402

APP_TITLE = "Фото на документ по требованиям МВД"

# Режим «круглая голова»: определяется автоматически или задаётся вручную.
ROUND_MODES = (("auto", "Определить по лицу"),
               ("yes", "Круглая голова"),
               ("no", "Обычная голова"))


# ── Диалог выбора размера ───────────────────────────────────────────────────


def ask_round_face(parent) -> str:
    """Три состояния вместо галочки: автоматика и два ручных ответа."""
    import tkinter as tk
    from tkinter import ttk

    stored = config.get("round_face", "mode", "auto")
    if stored not in dict(ROUND_MODES):
        stored = "auto"
    current = tk.StringVar(value=stored)
    box = ttk.Frame(parent)
    label = ttk.Label(box, text="Голова:")
    label.pack(side="left")
    pick = ttk.Combobox(box, textvariable=current, state="readonly",
                        width=22, values=[text for _id, text in ROUND_MODES])
    pick.pack(side="left", padx=(6, 0))

    def remember(*_args):
        config.set_value("round_face", "mode", current.get())
        try:
            config.save()
        except OSError:
            pass

    pick.bind("<<ComboboxSelected>>", remember)

    def get_mode() -> str:
        for mode, _text in ROUND_MODES:
            if _text == current.get():
                return mode
        return "auto"

    return box, get_mode


class SizeDialog:
    """Выбор размера фотографии. Все размеры — в миллиметрах."""

    def __init__(self, presets: dict[str, dict]):
        import tkinter as tk
        from tkinter import ttk

        self.result: dict | None = None
        self.round_face_mode = "auto"
        # apply_settings() не отдаёт пустой список: если форматов в ini не
        # осталось, подставляются встроенные. Поэтому order здесь не пуст.
        self.presets = presets
        self.order = config.preset_order(presets)

        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.resizable(False, False)
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Размер фотографии:").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.choice = tk.StringVar(value=self.order[0])
        self.details: list = []
        for i, size_id in enumerate(self.order):
            ttk.Radiobutton(
                frame, text=self.presets[size_id]["label"], value=size_id,
                variable=self.choice, command=self._sync).grid(
                row=i + 1, column=0, sticky="w")
            info = ttk.Label(frame, text="", foreground="#555555")
            info.grid(row=i + 1, column=1, sticky="w", padx=(14, 0))
            self.details.append(info)

        row = len(self.order) + 1
        ttk.Separator(frame).grid(row=row, column=0, columnspan=2,
                                  sticky="ew", pady=10)
        self.custom_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Свой размер:",
                        variable=self.custom_var,
                        command=self._sync).grid(row=row + 1, column=0, sticky="w")
        size_box = ttk.Frame(frame)
        size_box.grid(row=row + 1, column=1, sticky="w", padx=(14, 0))
        self.custom_w = tk.StringVar(value="37")
        self.custom_h = tk.StringVar(value="47")
        self.entry_w = ttk.Entry(size_box, textvariable=self.custom_w, width=6)
        self.entry_w.pack(side="left")
        ttk.Label(size_box, text=" × ").pack(side="left")
        self.entry_h = ttk.Entry(size_box, textvariable=self.custom_h, width=6)
        self.entry_h.pack(side="left")
        ttk.Label(size_box, text=" мм").pack(side="left", padx=(4, 0))

        # Отступы в миллиметрах. Пусто — берутся доли кадра из ini. Так можно
        # задать ширину лица и положение подбородка для любого своего размера.
        offsets = ttk.Frame(frame)
        offsets.grid(row=row + 2, column=0, columnspan=2, sticky="w",
                     padx=(0, 0), pady=(8, 0))
        self.face_w_mm = tk.StringVar(value="")
        self.chin_mm = tk.StringVar(value="")
        self.entry_face = self._offset_row(offsets, "Лицо:", self.face_w_mm)
        self.entry_chin = self._offset_row(offsets, "Подбородок снизу:",
                                           self.chin_mm)

        self.round_box, self._get_round = ask_round_face(frame)
        self.round_box.grid(row=row + 3, column=0, columnspan=2,
                            sticky="w", pady=(10, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=row + 4, column=0, columnspan=2, sticky="e",
                     pady=(14, 0))
        ttk.Button(buttons, text="Сделать", command=self._ok).pack(side="right")
        ttk.Button(buttons, text="Отмена", command=self.root.destroy).pack(
            side="right", padx=(0, 8))

        # Подсказка про цифры: без неё режим выглядит как магия.
        hint = "Цифра на нумпаде — выбрать размер и продолжить. Enter — подтвердить, Esc — отмена"
        if len(self.order) < 10:
            hint = f"Цифры 1…{len(self.order)} на нумпаде — выбрать размер и продолжить. " \
                   "Enter — подтвердить, Esc — отмена"
        ttk.Label(frame, text=hint, foreground="#555555").grid(
            row=row + 5, column=0, columnspan=2, sticky="w", pady=(10, 0))

        self.root.bind("<Return>", lambda _e: self._ok())
        self.root.bind("<Escape>", lambda _e: self.root.destroy())
        self.root.bind("<KeyPress>", self._digit_size)
        self._sync()
        bring_to_front(self.root)
        self.root.grab_set()

    def _digit_size(self, event):
        """Цифра на нумпаде выбирает размер и сразу продолжает работу.

        Нужно, чтобы не водить мышью: нажали «1» — и поехали. Работает и верхний
        ряд цифр, и нумпад; «0» и цифры длиннее списка игнорируются.
        """
        key = event.keysym
        if key.startswith("KP_"):
            key = key[3:]
        if len(key) != 1 or not key.isdigit() or key == "0":
            return None
        index = int(key) - 1
        if index >= len(self.order):
            return None
        self.choice.set(self.order[index])
        self._ok()
        return "break"       # цифру больше никуда не пускаем

    def _offset_row(self, parent, title: str, variable) -> object:
        """Строка «подпись: поле мм» — отступ задаётся в миллиметрах."""
        import tkinter as tk
        from tkinter import ttk

        line = ttk.Frame(parent)
        line.pack(side="left", padx=(0, 12))
        ttk.Label(line, text=title).pack(side="left")
        entry = ttk.Entry(line, textvariable=variable, width=6)
        entry.pack(side="left", padx=(6, 0))
        ttk.Label(line, text=" мм").pack(side="left", padx=(4, 0))
        return entry

    def _mm(self, variable) -> float | None:
        """Число из поля отступа. Пусто или мусор — None, то есть по доле кадра."""
        text = variable.get().strip().replace(",", ".")
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
        return value if value > 0 else None

    def _current(self) -> dict | None:
        if self.custom_var.get():
            try:
                width = float(self.custom_w.get().replace(",", "."))
                height = float(self.custom_h.get().replace(",", "."))
            except ValueError:
                return None
            if width <= 0 or height <= 0:
                return None
            preset = config.custom_preset(
                width, height,
                face_width_mm=self._mm(self.face_w_mm),
                chin_from_bottom_mm=self._mm(self.chin_mm))
            # Свой размер с отступами сохраняем в ini — введённые миллиметры
            # должны пережить перезапуск программы.
            return config.add_preset(
                width, height, preset=preset)
        return self.presets.get(self.choice.get())

    def _sync(self) -> None:
        for i, size_id in enumerate(self.order):
            self.details[i].configure(text=self._describe(self.presets[size_id]))
        # Поля своего размера гасятся, пока галочка не стоит.
        state = "normal" if self.custom_var.get() else "disabled"
        for entry in (self.entry_w, self.entry_h,
                      self.entry_face, self.entry_chin):
            entry.configure(state=state)

    @staticmethod
    def _describe(preset: dict) -> str:
        px_per_mm = preset["ppi"] / 25.4
        return (f"{round(preset['width_px'])} × {round(preset['height_px'])} px, "
                f"лицо {preset['face_width_mm']:.1f} мм, "
                f"подбородок {preset['chin_from_bottom_mm']:.1f} мм снизу")

    def _ok(self) -> None:
        preset = self._current()
        if preset is None:
            return
        self.result = preset
        self.round_face_mode = self._get_round()
        self.root.destroy()

    def ask(self) -> dict | None:
        self.root.mainloop()
        return self.result


def ask_size(presets: dict[str, dict]) -> tuple[dict | None, str]:
    """Выбор размера.

    Без окна работает, если размер задан заранее: аргументом командной строки
    (`passport.exe 30x40`) или в ini ([photoshop] auto_size). Это нужно для
    пакетной обработки и для проверок.
    """
    auto = os.environ.get("PASSPORT_AUTO_SIZE", "").strip() \
        or (sys.argv[1].strip() if len(sys.argv) > 1 else "") \
        or config.auto_size()
    mode = config.get("round_face", "mode", "auto")
    if mode not in dict(ROUND_MODES):
        mode = "auto"
    if auto:
        if auto.lower().startswith("свой:"):
            width, _, height = auto.partition(":")[2].partition("x")
            return config.custom_preset(float(width), float(height)), mode
        return presets.get(auto) or presets[config.BASE_PRESET_ID], mode
    dialog = SizeDialog(presets)
    result = dialog.ask()
    return result, dialog.round_face_mode


def show_message(title: str, text: str) -> None:
    """Простое окно с текстом. Нужно там, где консоли нет: у собранного exe
    stdout выводить некуда, и молча пройти мимо ошибки нельзя."""
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title(title)
    ttk.Label(root, text=text, wraplength=640, justify="left",
              font=("", 9)).pack(padx=14, pady=12)
    ttk.Button(root, text="ОК", command=root.destroy).pack(pady=(0, 12))
    root.bind("<Return>", lambda _e: root.destroy())
    root.bind("<Escape>", lambda _e: root.destroy())
    bring_to_front(root)
    root.mainloop()


def bring_to_front(root) -> None:
    """Показать окно поверх всего и отдать ему фокус.

    Иначе окно программы открывается под Photoshop — он ведь держит фокус, пока
    ждёт результата, — и пользователь не видит ни выбора размера, ни отчёта.
    """
    import tkinter as tk

    try:
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()
    except tk.TclError:
        pass


def show_report(title: str, lines: list[tuple[str, tuple]]) -> None:
    import tkinter as tk
    from tkinter import ttk

    if os.environ.get("PASSPORT_NO_REPORT") == "1" \
            or not config.get_bool("general", "show_report", True):
        print(title)
        for text, _style in lines:
            print("  " + text)
        return
    root = tk.Tk()
    root.title(title)
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=12)
    frame.pack(fill="both", expand=True)
    for i, (text, style) in enumerate(lines):
        ttk.Label(frame, text=text, font=style or None, wraplength=520,
                  justify="left").grid(row=i, column=0, sticky="w", pady=2)
    ttk.Button(frame, text="Закрыть", command=root.destroy).grid(
        row=len(lines), column=0, pady=(12, 0))
    root.bind("<Return>", lambda _e: root.destroy())
    root.bind("<Escape>", lambda _e: root.destroy())

    # Отчёт держит процесс живым, а процесс нужен Photoshop. Если оставить окно
    # до щелчка мышью, при пакетной работе копятся висящие экземпляры. Поэтому
    # окно закрывается само через отведённое время (в ini, 0 — не закрывать).
    seconds = config.get_int("general", "report_timeout_sec", 90)
    if seconds > 0:
        root.after(seconds * 1000, root.destroy)
    bring_to_front(root)
    root.mainloop()


# ── Расчёт ──────────────────────────────────────────────────────────────────


def plan(job: dict, preset: dict, round_face_mode: str) -> tuple[dict, dict]:
    """Считает трансформацию и собирает задание для Photoshop."""
    face, size = analyse_path(job["temp"])
    transform = geometry.solve_transform(face, size, preset, round_face_mode)

    doc_w = round(preset["width_mm"] * transform.ppi / 25.4)
    doc_h = round(preset["height_mm"] * transform.ppi / 25.4)

    source_dir = Path(job.get("sourcePath") or ".").parent
    subdir = config.get("general", "output_subdir")
    output_dir = source_dir / subdir if subdir else source_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    save_format = config.get("general", "save_format", "JPEG").upper()
    ext = {"JPEG": "jpg", "PSD": "psd", "TIFF": "tif"}.get(save_format, "jpg")
    stem = Path(job["source"]).stem
    suffix = config.get("general", "output_suffix", "_3,7x4,7см")
    suffix = "_" + (preset.get("suffix") or suffix) if suffix else ""
    result = output_dir / f"{stem}{suffix}.{ext}"

    template = ""
    if preset.get("template"):
        candidate = config.templates_dir() / preset["template"]
        if candidate.is_file():
            template = str(candidate)

    request = {
        "source": job["source"],
        "template": template,
        "docWidth": doc_w,
        "docHeight": doc_h,
        "ppi": transform.ppi,
        "rotateDeg": round(transform.rotate_deg, 4),
        "scalePercent": round(transform.scale * 100, 4),
        "sourceWidth": transform.source_size[0],
        "sourceHeight": transform.source_size[1],
        "targetCx": round(transform.target_center[0], 3),
        "targetCy": round(transform.target_center[1], 3),
        "tx": round(transform.translate[0], 3),
        "ty": round(transform.translate[1], 3),
        "result": str(result),
        "format": save_format,
        "quality": config.get_int("general", "jpeg_quality", 12),
    }
    return request, transform.report


def measure_result(path: str, preset: dict) -> dict:
    """Перепроверка готового файла тем же распознаванием."""
    px_per_mm = preset["ppi"] / 25.4
    doc_h = round(preset["height_mm"] * px_per_mm)
    face, _ = analyse_path(path)
    measures = geometry.measure_face(face.lm106)
    verified = {
        "face_width_mm": measures.face_width / px_per_mm,
        "chin_from_bottom_mm": doc_h / px_per_mm - measures.chin[1] / px_per_mm,
        "eye_line_deg": geometry.tilt_signals(face.lm106)[0],
    }
    # Запас над волосами в готовом файле. Готовый файл — идеальный случай для
    # замера: фон ровный, кадр известен. Если исходник был не тот, здесь это
    # покажет — в отчёте появится строка о расхождении.
    verified["headroom_mm"] = None if face.hair_top is None \
        else face.hair_top / px_per_mm
    return verified


def covers_canvas(done: dict) -> bool:
    """Закрывает ли фотография весь кадр: если нет, по краям будет пусто."""
    try:
        return (float(done["left"]) <= 0.5 and float(done["top"]) <= 0.5
                and float(done["right"]) >= float(done["docWidth"]) - 0.5
                and float(done["bottom"]) >= float(done["docHeight"]) - 0.5)
    except (KeyError, ValueError):
        return True


def report_lines(report: dict, result: str, verified: dict | None,
                 done: dict) -> list[tuple[str, tuple]]:
    small = ("", 9)
    lines: list[tuple[str, tuple]] = [(report["document"], ("", 10, "bold"))]
    lines.append((f"Поворот {report['rotate_deg']:+.2f}°   "
                  f"масштаб {report['scale_percent']:.1f}%", small))
    lines.append((f"Лицо по скулам {report['face_width_mm']:.2f} мм "
                  f"(норма {report['norm_width_mm'][0]:.0f}…"
                  f"{report['norm_width_mm'][1]:.0f} мм)", small))
    if report.get("hair_found"):
        lines.append((f"Запас над волосами {report['headroom_mm']:.2f} мм "
                      f"(цель {report['headroom_target_mm']:.2f} мм)", small))
        if report.get("chin_floor_applied"):
            lines.append((f"Подбородок опущен до границы "
                          f"{report['chin_floor_mm']:.1f} мм — волосы не влезли "
                          f"в обычный запас", small))
        elif report.get("headroom_ceiling_applied"):
            lines.append((f"Запас увеличен: подбородок не может быть выше "
                          f"{report['chin_ceiling_mm']:.1f} мм", small))
    else:
        lines.append(("Запас над волосами: волосы не нашлись, положение "
                      "считано по подбородку", small))
    lines.append((f"Подбородок {report['chin_from_bottom_mm']:.2f} мм "
                  f"от нижнего края", small))
    lines.append((f"Наклон линии глаз {report['eye_line_deg']:+.2f}°", small))
    lines.append((f"Макушка → подбородок ≈{report['crown_to_chin_mm']:.1f} мм "
                  f"(норма {report['norm_height_mm'][0]:.0f}…"
                  f"{report['norm_height_mm'][1]:.0f} мм)", small))

    if report.get("round_face"):
        lines.append((f"Круглая голова: овал/ширина {report['round_face_oval_ratio']:.3f}, "
                      f"подбородок-глаза/ширина "
                      f"{report['round_face_chin_eye_ratio']:.3f}, "
                      f"глаза/ширина {report['round_face_eye_ratio']:.3f} — "
                      f"+{report['round_face_add_mm']:.1f} мм по ширине, "
                      f"+{report['round_face_up_mm']:.1f} мм вверх", small))
    lines.append(("", small))

    if not covers_canvas(done):
        lines.append(("! Фотография не закрывает весь кадр — по краям "
                      "будет пустое поле.", small))
    for text, ok in (("width_in_range", "ширина лица вне нормы"),
                     ("crown_in_range", "высота головы вне нормы")):
        if not report[text]:
            lines.append(("! " + ok, small))

    if verified:
        agree = (abs(verified["face_width_mm"] - report["face_width_mm"]) <= 0.35
                 and abs(verified["chin_from_bottom_mm"]
                         - report["chin_from_bottom_mm"]) <= 0.35
                 and abs(verified["eye_line_deg"]) <= 0.5)
        head = ""
        if verified.get("headroom_mm") is not None:
            head = f", запас над волосами {verified['headroom_mm']:.2f} мм"
        mark = "✓" if agree else "!"
        lines.append((f"{mark} Готовый файл: лицо {verified['face_width_mm']:.2f} мм, "
                      f"подбородок {verified['chin_from_bottom_mm']:.2f} мм"
                      f"{head}, "
                      f"наклон {verified['eye_line_deg']:+.2f}°", small))
        if not agree:
            lines.append(("! Результат разошёлся с расчётом — проверьте глазами.",
                          small))
    lines.append((Path(result).name, ("", 9, "bold")))
    lines.append((str(Path(result).parent), small))
    return lines


# ── Основной ход ────────────────────────────────────────────────────────────


def warn_about_ini() -> None:
    problem = config.ini_error()
    if problem:
        show_message("Ошибка в passport.ini",
                     f"Файл настроек не удалось прочитать: {problem}\n\n"
                     "Пока вы не исправите ошибку, программа работает по "
                     "встроенным значениям. Исправьте синтаксис в файле "
                     f"{config.ini_path().name} рядом с программой.")


def main() -> int:
    job = bridge.read_job()
    presets = config.apply_settings()
    warn_about_ini()

    preset, round_face_mode = ask_size(presets)
    if preset is None:
        # Пользователь закрыл окно: Photoshop должен это понять и убрать за собой.
        bridge.cleanup()
        bridge.cancel()
        return 0

    request, report = plan(job, preset, round_face_mode)
    bridge.write_transform(request)
    done = bridge.wait_done()
    result = done.get("result", request["result"])

    verified = None
    try:
        verified = measure_result(result, preset)
    except (FaceNotFound, OSError, ValueError):
        pass

    bridge.cleanup()
    show_report("Готово", report_lines(report, result, verified, done))
    return 0


def run() -> int:
    """main с человеческими сообщениями обо всех сбоях.

    Текст ошибки пишется ещё и в stderr и в папку работы:error.txt — окно
    сообщения живёт недолго, а разбираться потом придётся по файлу.
    """
    try:
        return main()
    except Exception as exc:  # noqa: BLE001 — пользователю нужен текст ошибки
        text = traceback.format_exc()
        print(text, file=sys.stderr)
        try:
            (bridge.work_dir() / "error.txt").write_text(text, encoding="utf-8")
        except OSError:
            pass
        bridge.cleanup()
        # Отказ Photoshop должен узнать ПОСЛЕ уборки: cleanup удаляет и
        # transform.txt, а значит и только что записанный отказ.
        bridge.cancel()
        bridge.clear_logs()
        if isinstance(exc, FaceNotFound):
            show_report("Лицо не найдено", [
                ("В кадре не нашлось лица.", ("", 10)),
                ("Проверьте освещение и что лицо не закрыто волосами или рукой.",
                 ("", 9)),
            ])
            return 1
        title = "Ошибка Photoshop" if isinstance(exc, bridge.BridgeError) \
            else "Ошибка"
        lines = [(f"{type(exc).__name__}: {exc}"[:600], ("", 10))]
        ini_problem = config.ini_error()
        if ini_problem:
            lines.append((f"Файл настроек не прочитан, взяты значения по "
                          f"умолчанию: {ini_problem}", ("", 9)))
        log = bridge.read_last_log()
        if log.strip():
            lines.append(("", ("", 9)))
            lines.append(("Подробности — в последней строке журнала "
                          "папки работы:", ("", 9)))
            lines.append((log.strip()[-500:], ("", 8)))
        show_report(title, lines)
        return 1


HELP = """passport — фото на документ по требованиям МВД.
  без аргументов  работать с заданием от Photoshop
  размер          обработать задание сразу в этом размере (например 37x47)
  install         поставить скрипт в Photoshop
  settings        открыть passport.ini в блокноте
  --log ФАЙЛ      писать весь вывод в ФАЙЛ (так вызывает Photoshop)"""


def open_log(path: str) -> None:
    """Перенаправить вывод в файл журнала.

    Нужно потому, что программу запускает Photoshop. Старый способ — bat с
    `start /b` и `> журнал` — оставляет программу в консоли bat, и чёрное окно
    висит всё время её работы. Теперь bat только отпускает программу, а журнал
    (его потом читает bridge.read_last_log и на него ссылается скрипт Photoshop)
    пишется здесь.
    """
    if not path:
        return
    try:
        stream = open(path, "w", encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"не удалось открыть журнал {path}: {exc}", file=sys.stderr)
        return
    sys.stdout = stream
    sys.stderr = stream


def install_and_report() -> int:
    """Установка скрипта с результатом на экране.

    У собранного exe консоли нет, поэтому и «ничего не происходит», и «ничего
    не пишет» — это один и тот же случай: сообщение уходит в никуда. Поэтому
    результат установки показывается окном всегда, в том числе когда ничего не
    получилось.
    """
    lines: list[str] = []
    code = installer.install(verbose=False, report=lines)
    show_message("Установка в Photoshop" if code == 0 else "Установка не удалась",
                 "\n".join(lines) or "Подробности в install.log")
    return code


def main_entry() -> int:
    """Точка входа, общая для запуска из исходников и из собранного exe."""
    argv = list(sys.argv[1:])
    if "--log" in argv:
        index = argv.index("--log")
        log_path = argv[index + 1] if index + 1 < len(argv) else ""
        del argv[index:index + 2]
        sys.argv = [sys.argv[0]] + argv
        open_log(log_path)
    args = [a.strip() for a in argv]
    command = args[0].lower() if args else ""
    try:
        if command == "install":
            return install_and_report()
        if command == "settings":
            path = config.ini_path()      # файл создаётся при разборе ini
            config.parser()
            os.startfile(str(path))       # noqa: S606 — открыть блокнот
            return 0
        if command in ("help", "/?", "-h", "--help"):
            print(HELP)
            return 0
        return run()
    except Exception as exc:  # noqa: BLE001 — у собранного exe нет консоли
        text = traceback.format_exc()
        try:
            (config.work_dir() / "error.txt").write_text(text, encoding="utf-8")
        except OSError:
            pass
        print(text, file=sys.stderr)
        show_message("Ошибка", f"{type(exc).__name__}: {exc}"[:800])
        return 1


if __name__ == "__main__":
    raise SystemExit(main_entry())