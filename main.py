"""Application entry point."""

import sys
from pathlib import Path

# Make sure the package is importable when running directly
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from src.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("OcarinaTabber")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("OcarinaTabber")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
