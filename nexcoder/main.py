"""NexCoder entry point — launches the PySide6 desktop application."""

import sys
import os

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv


def _load_env() -> None:
    """Load .env, resolving it whether running from source or a frozen exe.

    A PyInstaller build resolves ``__file__`` inside the bundle, so the
    source-relative path never finds the user's project ``.env``. When
    frozen we look next to the executable (and its parents) first, so the
    packaged app honours NEXA_* settings just like the dev run.
    """
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates += [
            os.path.join(exe_dir, ".env"),
            os.path.join(os.path.dirname(exe_dir), ".env"),
            os.path.join(os.path.dirname(os.path.dirname(exe_dir)), ".env"),
        ]
    candidates.append(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    candidates.append(os.path.join(os.getcwd(), ".env"))
    for path in candidates:
        if os.path.isfile(path):
            load_dotenv(path)
            return


def dispatch() -> None:
    args = sys.argv[1:]
    if args:
        if args[0] == "cli":
            from nexcoder.cli import main as cli_main
            raise SystemExit(cli_main(args[1:] + ["--interactive"]))
        if args[0] == "start" and len(args) > 1 and args[1] == "cli":
            from nexcoder.cli import main as cli_main
            raise SystemExit(cli_main(args[2:] + ["--interactive"]))
    main()


def main() -> None:
    """Launch the NexCoder desktop application."""
    _load_env()

    # Import PySide6 after env is loaded
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QPalette, QColor, QIcon

    # High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("NexCoder")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("Nexa")

    # Set dark palette
    palette = QPalette()
    bg = QColor("#0e0e14")
    surface = QColor("#16161e")
    text_primary = QColor("#e0e0e8")
    text_secondary = QColor("#8888a0")
    accent = QColor("#6c5ce7")
    border = QColor("#2a2a3a")

    palette.setColor(QPalette.ColorRole.Window, surface)
    palette.setColor(QPalette.ColorRole.WindowText, text_primary)
    palette.setColor(QPalette.ColorRole.Base, bg)
    palette.setColor(QPalette.ColorRole.AlternateBase, surface)
    palette.setColor(QPalette.ColorRole.ToolTipBase, surface)
    palette.setColor(QPalette.ColorRole.ToolTipText, text_primary)
    palette.setColor(QPalette.ColorRole.Text, text_primary)
    palette.setColor(QPalette.ColorRole.Button, surface)
    palette.setColor(QPalette.ColorRole.ButtonText, text_primary)
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Link, accent)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, text_secondary)
    palette.setColor(QPalette.ColorRole.Light, border)
    palette.setColor(QPalette.ColorRole.Midlight, border)
    palette.setColor(QPalette.ColorRole.Dark, bg)
    palette.setColor(QPalette.ColorRole.Mid, border)
    palette.setColor(QPalette.ColorRole.Shadow, QColor("#000000"))

    app.setPalette(palette)

    # Set default font
    font = QFont("Inter", 10)
    app.setFont(font)

    # Set app icon (if available)
    resources_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")
    for icon_name in ("icon.ico", "icon.png"):
        icon_path = os.path.join(resources_dir, icon_name)
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            break

    # Global stylesheet for native Qt widgets (title bar, menus, scrollbars)
    app.setStyleSheet("""
        QMainWindow {
            background-color: #0e0e14;
        }
        QMenuBar {
            background-color: #16161e;
            color: #e0e0e8;
            border-bottom: 1px solid #2a2a3a;
            padding: 2px 0;
        }
        QMenuBar::item {
            padding: 4px 12px;
            border-radius: 4px;
        }
        QMenuBar::item:selected {
            background-color: #2d2d44;
        }
        QMenu {
            background-color: #1a1a26;
            color: #e0e0e8;
            border: 1px solid #2a2a3a;
            border-radius: 8px;
            padding: 4px;
        }
        QMenu::item {
            padding: 6px 24px;
            border-radius: 4px;
        }
        QMenu::item:selected {
            background-color: #2d2d44;
        }
        QMenu::separator {
            height: 1px;
            background-color: #2a2a3a;
            margin: 4px 8px;
        }
        QToolTip {
            background-color: #1a1a26;
            color: #e0e0e8;
            border: 1px solid #2a2a3a;
            border-radius: 4px;
            padding: 4px 8px;
        }
    """)

    # Import and create main window
    from nexcoder.app import MainWindow

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
