"""Проверка окна выбора размера без Photoshop.

Окно не показывается: создаётся, переключается на «свой размер», проверяется,
что числа разбираются, и нажимается «Сделать». Ловит ошибки вёрстки — их видно
только здесь, в остальных прогонах размер передаётся аргументом.

    python tools\\test_dialog.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Проверка дописывает свой размер в ini — поэтому работаем на копии настроек,
# а не на вашей. PASSPORT_INI переопределяет путь к файлу, и переменная должна
# быть задана ДО импорта pp.config.
_TEST_INI = Path(tempfile.gettempdir()) / "passport_test_dialog.ini"
_TEST_INI.unlink(missing_ok=True)
os.environ["PASSPORT_INI"] = str(_TEST_INI)

import passport  # noqa: E402
from pp import config  # noqa: E402


def check(name: str, got, expected) -> bool:
    ok = got == expected
    print(f"  {'✓' if ok else '✗'} {name}: {got}"
          + ("" if ok else f" (ожидалось {expected})"))
    return ok


def main() -> int:
    presets = config.apply_settings()
    passed = True

    print("окно выбора размера")
    dialog = passport.SizeDialog(presets)
    try:
        passed &= check("размеров в списке", len(dialog.order), len(presets))
        passed &= check("по умолчанию выбран", dialog.choice.get(),
                        config.BASE_PRESET_ID)
        passed &= check("поля своего размера гасятся",
                        str(dialog.entry_w.cget("state")), "disabled")

        # Переключаем на «свой размер» — поля должны проснуться.
        dialog.custom_var.set(True)
        dialog._sync()
        passed &= check("после галочки поля разблокированы",
                        str(dialog.entry_w.cget("state")), "normal")

        dialog.custom_w.set("30")
        dialog.custom_h.set("40")
        preset = dialog._current()
        passed &= check("свой размер 30×40 мм", round(preset["width_mm"]), 30)
        passed &= check("у него 900×1200 px",
                        (round(preset["width_mm"] * preset["ppi"] / 25.4),
                         round(preset["height_mm"] * preset["ppi"] / 25.4)),
                        (900, 1200))
        passed &= check("без отступов лицо по доле кадра",
                        round(preset["face_width_mm"], 1), 15.0)

        # Отступы в миллиметрах — то, ради чего размер и добавляют.
        dialog.face_w_mm.set("16,5")
        dialog.chin_mm.set("11")
        preset = dialog._current()
        passed &= check("лицо 16,5 мм задано", round(preset["face_width_mm"], 2), 16.5)
        passed &= check("подбородок 11 мм задан",
                        round(preset["chin_from_bottom_mm"], 2), 11.0)
        passed &= check("отступы сохранены в ini",
                        round(config.apply_settings()["30x40"]["face_width_mm"], 2),
                        16.5)
        dialog.face_w_mm.set("")
        dialog.chin_mm.set("")

        # Мусор в полях не должен приводить к падению — просто игнорируется.
        dialog.custom_w.set("ерунда")
        passed &= check("мусор в поле не ломает", dialog._current(), None)

        # Возврат к готовому размеру.
        dialog.custom_var.set(False)
        dialog.choice.set("30x40")
        preset = dialog._current()
        passed &= check("готовый 3×4", (round(preset["width_mm"]),
                                        round(preset["height_mm"])), (30, 40))
        passed &= check("имя файла", preset["suffix"], "3x4см")

        # «Сделать» закрывает окно и возвращает выбранное.
        passed &= check("режим головы из ini", dialog._get_round(), "auto")
        dialog._ok()
        passed &= check("выбран 3×4", dialog.result["id"], "30x40")
        # _ok() уже закрыл окно, звать destroy второй раз нельзя.

        # Цифра выбирает размер и сразу продолжает работу, поэтому после нажатия окна
        # уже нет — каждую цифру проверяем на свежем окне.
        # Нумпад синтетическим событием не проверить: у Tk на этой машине нет
        # таблицы кодов клавиш для KP_n, и event_generate их не создаёт. Поэтому
        # обработчик зовём с поддельным событием, а цифры верхнего ряда —
        # настоящим event_generate.
        class FakeKey:
            def __init__(self, keysym):
                self.keysym = keysym

        def press(keysym: str) -> dict | None:
            window = passport.SizeDialog(presets)
            try:
                if keysym.isdigit():
                    window.root.event_generate("<KeyPress>", keysym=keysym)
                else:
                    window._digit_size(FakeKey(keysym))
                return window.result
            finally:
                try:
                    window.root.destroy()
                except Exception:  # noqa: BLE001 — окно уже закрыто нажатием
                    pass

        passed &= check("цифра 2 с нумпада выбрала второй размер",
                        press("KP_2")["id"], "30x40")
        passed &= check("цифра 1 с нумпада выбрала первый",
                        press("KP_1")["id"], "37x47")
        passed &= check("цифра 3 с верхнего ряда выбрала третий",
                        press("3")["id"], "35x45")
        passed &= check("цифра вне списка ничего не делает",
                        press("KP_9"), None)
        passed &= check("ноль игнорируется", press("KP_0"), None)
        passed &= check("не цифра игнорируется", press("Return"), None)
    except Exception:
        try:
            dialog.root.destroy()
        except Exception:  # noqa: BLE001
            pass
        raise

    print()
    print("  всё верно" if passed else "  есть расхождения")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())