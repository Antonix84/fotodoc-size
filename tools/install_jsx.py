"""Ставит passport-photo.jsx в Photoshop и пишет рядом с ним пути.

    python tools\\install_jsx.py       из исходников
    passport.exe install               из собранной программы

Тот же самый код живёт в pp/installer.py — отличается только обёртка.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pp import installer  # noqa: E402


def main() -> int:
    return installer.install()


if __name__ == "__main__":
    raise SystemExit(main())