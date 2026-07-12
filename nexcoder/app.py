"""MainWindow — PySide6 window hosting the QWebEngineView with React frontend."""

import os
import json

from PySide6.QtWidgets import QMainWindow, QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QUrl, QSettings, Qt, QSize
from PySide6.QtGui import QAction, QKeySequence


class MainWindow(QMainWindow):
    """NexCoder main window — hosts the entire UI via QWebEngineView."""

    def __init__(self) -> None:
        super().__init__()

        self._project_name = "NexCoder"
        self._settings = QSettings("Nexa", "NexCoder")

        self._setup_window()
        self._setup_web_view()
        self._setup_bridge()
        self._setup_menu_bar()
        self._restore_geometry()

    # ── Window Setup ──────────────────────────────────────────────────

    def _setup_window(self) -> None:
        """Configure the main window properties."""
        self.setWindowTitle("NexCoder")
        self.setMinimumSize(QSize(1200, 800))

        # Remove default window padding
        self.setContentsMargins(0, 0, 0, 0)

    def _setup_web_view(self) -> None:
        """Create and configure the QWebEngineView as the central widget."""
        self._web_view = QWebEngineView(self)
        self.setCentralWidget(self._web_view)

        # Configure web engine settings
        settings = self._web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)

        # Set dark background to prevent white flash on load
        self._web_view.page().setBackgroundColor(Qt.GlobalColor.black)

        # Load the React frontend
        ui_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "resources", "ui", "index.html"
        )

        if os.path.exists(ui_path):
            self._web_view.setUrl(QUrl.fromLocalFile(ui_path))
        else:
            # Development fallback: load from Vite dev server
            self._web_view.setUrl(QUrl("http://localhost:5173"))

    def _setup_bridge(self) -> None:
        """Set up QWebChannel to bridge Python ↔ JavaScript."""
        from nexcoder.bridge import Bridge

        self._channel = QWebChannel(self._web_view.page())
        self._bridge = Bridge(self)
        self._channel.registerObject("bridge", self._bridge)
        self._web_view.page().setWebChannel(self._channel)

    # ── Menu Bar ──────────────────────────────────────────────────────

    def _setup_menu_bar(self) -> None:
        """Create the native menu bar."""
        menu_bar = self.menuBar()

        # ── File Menu ──
        file_menu = menu_bar.addMenu("&File")

        open_folder = QAction("Open Folder...", self)
        open_folder.setShortcut(QKeySequence("Ctrl+O"))
        open_folder.triggered.connect(self._on_open_folder)
        file_menu.addAction(open_folder)

        file_menu.addSeparator()

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(lambda: self._bridge.trigger_save())
        file_menu.addAction(save_action)

        save_as = QAction("Save As...", self)
        save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as.triggered.connect(lambda: self._bridge.trigger_save_as())
        file_menu.addAction(save_as)

        save_all = QAction("Save All", self)
        save_all.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_all.triggered.connect(lambda: self._bridge.trigger_save_all())
        file_menu.addAction(save_all)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence("Alt+F4"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # ── Edit Menu ──
        edit_menu = menu_bar.addMenu("&Edit")

        undo = QAction("Undo", self)
        undo.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(undo)

        redo = QAction("Redo", self)
        redo.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(redo)

        edit_menu.addSeparator()

        find = QAction("Find", self)
        find.setShortcut(QKeySequence.StandardKey.Find)
        edit_menu.addAction(find)

        replace = QAction("Replace", self)
        replace.setShortcut(QKeySequence("Ctrl+H"))
        edit_menu.addAction(replace)

        # ── View Menu ──
        view_menu = menu_bar.addMenu("&View")

        toggle_sidebar = QAction("Toggle Sidebar", self)
        toggle_sidebar.setShortcut(QKeySequence("Ctrl+B"))
        toggle_sidebar.triggered.connect(lambda: self._run_js("window.nexcoder?.toggleSidebar()"))
        view_menu.addAction(toggle_sidebar)

        toggle_terminal = QAction("Toggle Terminal", self)
        toggle_terminal.setShortcut(QKeySequence("Ctrl+`"))
        toggle_terminal.triggered.connect(lambda: self._run_js("window.nexcoder?.toggleTerminal()"))
        view_menu.addAction(toggle_terminal)

        toggle_ai = QAction("Toggle AI Panel", self)
        toggle_ai.setShortcut(QKeySequence("Ctrl+Shift+A"))
        toggle_ai.triggered.connect(lambda: self._run_js("window.nexcoder?.toggleAIPanel()"))
        view_menu.addAction(toggle_ai)

        view_menu.addSeparator()

        zoom_in = QAction("Zoom In", self)
        zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        zoom_in.triggered.connect(lambda: self._web_view.setZoomFactor(self._web_view.zoomFactor() + 0.1))
        view_menu.addAction(zoom_in)

        zoom_out = QAction("Zoom Out", self)
        zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        zoom_out.triggered.connect(lambda: self._web_view.setZoomFactor(self._web_view.zoomFactor() - 0.1))
        view_menu.addAction(zoom_out)

        reset_zoom = QAction("Reset Zoom", self)
        reset_zoom.setShortcut(QKeySequence("Ctrl+0"))
        reset_zoom.triggered.connect(lambda: self._web_view.setZoomFactor(1.0))
        view_menu.addAction(reset_zoom)

        # ── Terminal Menu ──
        terminal_menu = menu_bar.addMenu("&Terminal")

        new_terminal = QAction("New Terminal", self)
        new_terminal.setShortcut(QKeySequence("Ctrl+Shift+`"))
        new_terminal.triggered.connect(lambda: self._run_js("window.nexcoder?.newTerminal()"))
        terminal_menu.addAction(new_terminal)

        # ── Help Menu ──
        help_menu = menu_bar.addMenu("&Help")

        about = QAction("About NexCoder", self)
        about.triggered.connect(self._on_about)
        help_menu.addAction(about)

    # ── Actions ───────────────────────────────────────────────────────

    def _on_open_folder(self) -> None:
        """Open a folder via the bridge dialog handler."""
        self._bridge.open_folder_dialog()

    def _on_about(self) -> None:
        """Show about dialog."""
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.about(
            self,
            "About NexCoder",
            "<h2>NexCoder v0.1.0</h2>"
            "<p>AI-First Code Editor for the Nexa Ecosystem</p>"
            "<p>Powered by Nexa AI · Built with PySide6 + React + Monaco</p>"
        )

    # ── Helpers ───────────────────────────────────────────────────────

    def _run_js(self, code: str) -> None:
        """Execute JavaScript in the web view."""
        self._web_view.page().runJavaScript(code)

    def set_project_name(self, name: str) -> None:
        """Update the window title with the current project name."""
        self._project_name = name
        self.setWindowTitle(f"NexCoder — {name}")

    # ── Geometry Persistence ──────────────────────────────────────────

    def _restore_geometry(self) -> None:
        """Restore saved window geometry and state."""
        geometry = self._settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            # Default: centered, 80% of screen
            screen = QApplication.primaryScreen()
            if screen:
                available = screen.availableGeometry()
                width = int(available.width() * 0.8)
                height = int(available.height() * 0.85)
                x = available.x() + (available.width() - width) // 2
                y = available.y() + (available.height() - height) // 2
                self.setGeometry(x, y, width, height)

        state = self._settings.value("windowState")
        if state:
            self.restoreState(state)

    def closeEvent(self, event) -> None:
        """Save window geometry on close."""
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState())
        super().closeEvent(event)
