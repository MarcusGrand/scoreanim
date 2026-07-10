"""Application entry point (Phase 2 shell: static paged score display)."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from scoreanim.render.fonts import register_bravura
    from scoreanim.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    if not register_bravura():
        print("note: Bravura text font unavailable — the metronome-note "
              "glyph falls back to tofu (BACKLOG item 3)", file=sys.stderr)

    score = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    window = MainWindow(score)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
