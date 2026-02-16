from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from app.core.theme_service import ThemeService
from app.infra.config_store import ConfigStore
from app.infra.logger import setup_logger
from app.ui.main_window import MainWindow


def main() -> None:
    setup_logger()
    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Subtitle Workbench")
    icon_path = Path(__file__).resolve().parents[1] / "resources" / "icon" / "app.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    theme = ThemeService()
    app.setStyleSheet(theme.load_stylesheet())

    window = MainWindow(ConfigStore())
    window.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
