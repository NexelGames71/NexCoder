"""DialogHandler — Native Qt dialogs for file operations and confirmations."""

import os
from typing import Any

from PySide6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QInputDialog,
)


class DialogHandler:
    """Provides native OS dialogs via Qt."""

    def __init__(self, parent: Any = None) -> None:
        self._parent = parent

    def open_folder(self) -> str | None:
        """Show a native folder picker dialog. Returns path or None."""
        folder = QFileDialog.getExistingDirectory(
            self._parent,
            "Open Project Folder",
            os.path.expanduser("~"),
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )
        return folder if folder else None

    def select_folder(self, title: str = "Select Folder") -> str | None:
        """Show a native folder picker without implying project open."""
        folder = QFileDialog.getExistingDirectory(
            self._parent,
            title,
            os.path.expanduser("~"),
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )
        return folder if folder else None

    def open_file(self, title: str = "Open File", filters: str = "All Files (*)") -> str | None:
        """Show a native file open dialog."""
        file_path, _ = QFileDialog.getOpenFileName(
            self._parent, title, os.path.expanduser("~"), filters
        )
        return file_path if file_path else None

    def save_file(
        self,
        title: str = "Save File",
        filters: str = "All Files (*)",
        initial_path: str | None = None,
    ) -> str | None:
        """Show a native file save dialog."""
        file_path, _ = QFileDialog.getSaveFileName(
            self._parent, title, initial_path or os.path.expanduser("~"), filters
        )
        return file_path if file_path else None

    def confirm(self, title: str, message: str) -> bool:
        """Show a confirmation dialog. Returns True if user confirms."""
        result = QMessageBox.question(
            self._parent,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    def input_text(self, title: str, label: str, default: str = "") -> str | None:
        """Show a text input dialog. Returns text or None."""
        text, ok = QInputDialog.getText(self._parent, title, label, text=default)
        return text if ok else None

    def show_error(self, title: str, message: str) -> None:
        """Show an error message box."""
        QMessageBox.critical(self._parent, title, message)

    def show_info(self, title: str, message: str) -> None:
        """Show an informational message box."""
        QMessageBox.information(self._parent, title, message)

    def show_warning(self, title: str, message: str) -> None:
        """Show a warning message box."""
        QMessageBox.warning(self._parent, title, message)
