"""MainWindow - PySide6 window hosting the QWebEngineView with React frontend."""

import os
import json
import html

from PySide6.QtWidgets import QMainWindow, QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEnginePage
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QUrl, QSettings, Qt, QSize, QStandardPaths, QTimer
from PySide6.QtGui import QAction, QKeySequence


class NexCoderWebPage(QWebEnginePage):
    """Web page that records frontend console output for packaged diagnostics."""

    def javaScriptConsoleMessage(self, level, message: str, line_number: int, source_id: str) -> None:
        print(f"[NexCoder UI] {source_id}:{line_number}: {message}")
        super().javaScriptConsoleMessage(level, message, line_number, source_id)


class MainWindow(QMainWindow):
    """NexCoder main window - hosts the entire UI via QWebEngineView."""

    def __init__(self) -> None:
        super().__init__()

        self._project_name = "NexCoder"
        self._settings = QSettings("Nexa", "NexCoder")
        self._shell_stage = "initial"
        self._ide_geometry_restored = False
        self._frontend_path = ""
        self._frontend_probe_attempts = 0

        self._setup_window()
        self._setup_web_view()
        self._setup_bridge()
        self._setup_menu_bar()
        self._load_frontend()

    # Window Setup

    def _setup_window(self) -> None:
        """Configure the main window properties."""
        self.setWindowTitle("NexCoder")
        self.setMinimumSize(QSize(760, 540))

        # Remove default window padding
        self.setContentsMargins(0, 0, 0, 0)
        self._center_window(920, 640)

    def _setup_web_view(self) -> None:
        """Create and configure the QWebEngineView as the central widget."""
        profile_root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        if not profile_root:
            profile_root = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "NexCoder")
        web_profile_path = os.path.join(profile_root, "web-profile")
        os.makedirs(web_profile_path, exist_ok=True)
        profile = QWebEngineProfile.defaultProfile()
        profile.setPersistentStoragePath(web_profile_path)
        profile.setCachePath(os.path.join(web_profile_path, "cache"))
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)

        self._web_view = QWebEngineView(self)
        self._web_view.setPage(NexCoderWebPage(profile, self._web_view))
        self._web_view.loadFinished.connect(self._on_frontend_load_finished)
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

    def _load_frontend(self) -> None:
        """Load the React frontend after the QWebChannel bridge is registered."""
        self._frontend_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "resources", "ui", "index.html"
        )

        if os.path.exists(self._frontend_path):
            self._frontend_probe_attempts = 0
            self._web_view.setUrl(QUrl.fromLocalFile(self._frontend_path))
        else:
            # Development fallback: load from Vite dev server
            self._frontend_probe_attempts = 0
            self._web_view.setUrl(QUrl("http://localhost:5173"))

    def _show_native_boot_screen(self, message: str, detail: str = "") -> None:
        """Show a minimal visible page before the React bundle takes over."""
        safe_message = html.escape(message)
        safe_detail = html.escape(detail)
        detail_html = (
            f"<div style='margin-top:8px;color:#a8a3bd;font-size:13px;line-height:1.5'>{safe_detail}</div>"
            if detail else ""
        )
        self._web_view.setHtml(f"""
<!doctype html>
<html style="width:100%;height:100%;min-height:100vh;background:#0e0e14">
<body style="margin:0;width:100%;height:100%;min-height:100vh;overflow:hidden;background:#0e0e14;color:#f5f3ff;font-family:Inter,Segoe UI,sans-serif">
  <main style="width:100vw;height:100vh;display:flex;align-items:center;justify-content:center">
    <section style="width:min(390px,calc(100vw - 48px));text-align:center">
      <div style="width:48px;height:48px;margin:0 auto 18px;border-radius:14px;display:grid;place-items:center;background:#7c5cff;color:#fff;font-weight:800;font-size:24px;box-shadow:0 16px 44px rgba(124,92,255,.28)">N</div>
      <div style="font-size:18px;font-weight:700;letter-spacing:0">{safe_message}</div>
      {detail_html}
    </section>
  </main>
</body>
</html>
""")

    def _show_frontend_error(self, message: str, detail: str = "") -> None:
        self._show_native_boot_screen(message, detail)

    def _on_frontend_load_finished(self, ok: bool) -> None:
        href = self._web_view.url().toString()
        if href.startswith("data:text/html"):
            return
        if not ok and self._frontend_path:
            self._show_frontend_error(
                "NexCoder could not load the interface.",
                self._frontend_path,
            )
            return
        QTimer.singleShot(3500, self._verify_frontend_rendered)

    def _verify_frontend_rendered(self) -> None:
        js = """
(() => {
  const root = document.getElementById('root');
  const rect = root ? root.getBoundingClientRect() : null;
  const text = (document.body && document.body.innerText || '').trim();
  return JSON.stringify({
    href: window.location.href,
    textLength: text.length,
    text: text.slice(0, 160),
    rootFound: Boolean(root),
    rootChildren: root ? root.children.length : 0,
    width: rect ? rect.width : 0,
    height: rect ? rect.height : 0
  });
})()
"""
        self._web_view.page().runJavaScript(js, self._handle_frontend_probe)

    def _handle_frontend_probe(self, result: str) -> None:
        try:
            probe = json.loads(result) if result else {}
        except json.JSONDecodeError:
            probe = {}
        href = str(probe.get("href", ""))
        if href.startswith("data:text/html"):
            return
        text_length = int(probe.get("textLength") or 0)
        height = float(probe.get("height") or 0)
        root_found = bool(probe.get("rootFound"))
        if root_found and text_length > 0 and height > 0:
            return
        self._frontend_probe_attempts += 1
        if self._frontend_probe_attempts < 8:
            QTimer.singleShot(1000, self._verify_frontend_rendered)
            return
        self._show_frontend_error(
            "NexCoder opened, but the interface rendered blank.",
            (
                f"Loaded: {self._frontend_path or href}. "
                f"Probe: root={root_found}, text={text_length}, height={height}"
            ),
        )

    def _setup_bridge(self) -> None:
        """Set up QWebChannel to bridge Python and JavaScript."""
        from nexcoder.bridge import Bridge

        self._channel = QWebChannel(self._web_view.page())
        self._bridge = Bridge(self)
        self._channel.registerObject("bridge", self._bridge)
        self._web_view.page().setWebChannel(self._channel)

    # Menu Bar

    def _setup_menu_bar(self) -> None:
        """Create the native menu bar."""
        menu_bar = self.menuBar()

        # File Menu
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

        # Edit Menu
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

        # View Menu
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

        # Terminal Menu
        terminal_menu = menu_bar.addMenu("&Terminal")

        new_terminal = QAction("New Terminal", self)
        new_terminal.setShortcut(QKeySequence("Ctrl+Shift+`"))
        new_terminal.triggered.connect(lambda: self._run_js("window.nexcoder?.newTerminal()"))
        terminal_menu.addAction(new_terminal)

        # Help Menu
        help_menu = menu_bar.addMenu("&Help")

        about = QAction("About NexCoder", self)
        about.triggered.connect(self._on_about)
        help_menu.addAction(about)
        menu_bar.setVisible(False)

    # Actions

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
            "<p>Powered by Nexa AI - Built with PySide6 + React + Monaco</p>"
        )

    # Helpers

    def _run_js(self, code: str) -> None:
        """Execute JavaScript in the web view."""
        self._web_view.page().runJavaScript(code)

    def set_shell_stage(self, stage: str) -> None:
        """Switch native chrome between auth/setup and the full IDE."""
        self._apply_shell_stage(stage)

    def _center_window(self, width: int, height: int) -> None:
        screen = QApplication.primaryScreen()
        if not screen:
            self.resize(width, height)
            return
        available = screen.availableGeometry()
        width = min(width, available.width())
        height = min(height, available.height())
        x = available.x() + (available.width() - width) // 2
        y = available.y() + (available.height() - height) // 2
        self.setGeometry(x, y, width, height)

    def _apply_shell_stage(self, stage: str) -> None:
        normalized = stage if stage in {"auth", "ide"} else "auth"
        if normalized == self._shell_stage and normalized != "ide":
            return
        self._shell_stage = normalized

        if normalized == "auth":
            self.menuBar().setVisible(False)
            self.setWindowTitle("NexCoder")
            self.setMinimumSize(QSize(760, 540))
            self._center_window(920, 640)
            return

        self.menuBar().setVisible(True)
        self.setWindowTitle(
            f"NexCoder - {self._project_name}" if self._project_name != "NexCoder"
            else "NexCoder"
        )
        self.setMinimumSize(QSize(1200, 800))
        if not self._ide_geometry_restored:
            self._restore_geometry()
            self._ide_geometry_restored = True

    def set_project_name(self, name: str) -> None:
        """Update the window title with the current project name."""
        self._project_name = name
        if self._shell_stage == "ide":
            self.setWindowTitle(f"NexCoder - {name}")

    # Geometry Persistence

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
        """Save window geometry and stop child processes on close."""
        if self._shell_stage == "ide":
            self._settings.setValue("geometry", self.saveGeometry())
            self._settings.setValue("windowState", self.saveState())
        try:
            self._bridge._terminal.kill_all()
        except Exception:
            pass
        try:
            # Language-server node processes do not die with the parent
            # on Windows; shut them down explicitly.
            if self._bridge._lsp_manager is not None:
                self._bridge._lsp_manager.shutdown()
        except Exception:
            pass
        super().closeEvent(event)

