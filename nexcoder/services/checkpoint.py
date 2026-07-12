"""Checkpoint — file snapshot manager for safe rollback."""

import os
import shutil
import json
import time
import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_CHECKPOINTS = 10


class CheckpointManager:
    """Creates file snapshots before edits for safe rollback."""

    def __init__(self, project_root: str | None = None) -> None:
        self._root = project_root

    def set_project_root(self, root: str) -> None:
        """Set the project root directory."""
        self._root = os.path.abspath(root)

    def _checkpoints_dir(self) -> str:
        """Get the checkpoints directory path."""
        if not self._root:
            raise ValueError("No project root set")
        cp_dir = os.path.join(self._root, ".nexcoder", "checkpoints")
        os.makedirs(cp_dir, exist_ok=True)
        return cp_dir

    def create(self, files: list[str], label: str = "") -> str:
        """Create a checkpoint by copying specified files.

        Returns the checkpoint ID (timestamp).
        """
        timestamp = str(int(time.time() * 1000))
        cp_dir = os.path.join(self._checkpoints_dir(), timestamp)
        os.makedirs(cp_dir, exist_ok=True)

        manifest: dict[str, Any] = {
            "id": timestamp,
            "label": label,
            "created": time.time(),
            "files": [],
        }

        for file_path in files:
            abs_path = os.path.abspath(file_path)
            # Compute relative path from project root
            try:
                rel_path = os.path.relpath(abs_path, self._root)
            except ValueError:
                rel_path = os.path.basename(abs_path)

            if not os.path.isfile(abs_path):
                manifest["files"].append({
                    "original": abs_path.replace("\\", "/"),
                    "relative": rel_path.replace("\\", "/"),
                    "size": 0,
                    "existed": os.path.isdir(abs_path),
                    "type": "directory" if os.path.isdir(abs_path) else "missing",
                })
                continue

            # Create subdirectories in checkpoint
            dest = os.path.join(cp_dir, rel_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(abs_path, dest)

            manifest["files"].append({
                "original": abs_path.replace("\\", "/"),
                "relative": rel_path.replace("\\", "/"),
                "size": os.path.getsize(abs_path),
                "existed": True,
                "type": "file",
            })

        # Save manifest
        with open(os.path.join(cp_dir, "manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2)

        # Cleanup old checkpoints
        self._cleanup()

        logger.info(f"Created checkpoint {timestamp} with {len(manifest['files'])} files")
        return timestamp

    def restore(self, checkpoint_id: str, files: list[str] | None = None) -> dict[str, Any]:
        """Restore files from a checkpoint.

        If files is None, restores all files. Otherwise restores only specified files.
        """
        cp_dir = os.path.join(self._checkpoints_dir(), checkpoint_id)
        manifest_path = os.path.join(cp_dir, "manifest.json")

        if not os.path.isfile(manifest_path):
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")

        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        restored = []
        requested = None
        if files:
            requested = {
                value.replace("\\", "/")
                for value in files
            }
        created_directories: list[str] = []
        for file_info in manifest["files"]:
            original = file_info["original"]
            relative = file_info["relative"]
            existed = file_info.get("existed", True)
            entry_type = file_info.get("type", "file" if existed else "missing")

            # Filter if specific files requested
            if requested and original not in requested and relative not in requested:
                continue

            if not existed:
                if os.path.isfile(original):
                    os.unlink(original)
                    restored.append(original)
                elif os.path.isdir(original):
                    created_directories.append(original)
                continue

            if entry_type == "directory":
                os.makedirs(original, exist_ok=True)
                restored.append(original)
                continue

            backup = os.path.join(cp_dir, relative)
            if os.path.isfile(backup):
                os.makedirs(os.path.dirname(original), exist_ok=True)
                shutil.copy2(backup, original)
                restored.append(original)

        for directory in sorted(created_directories, key=len, reverse=True):
            try:
                os.rmdir(directory)
                restored.append(directory)
            except OSError:
                pass

        logger.info(f"Restored {len(restored)} files from checkpoint {checkpoint_id}")
        return {"restored": restored, "checkpoint_id": checkpoint_id}

    def add_file(self, checkpoint_id: str, file_path: str) -> None:
        """Snapshot one more file into an existing checkpoint.

        No-op when the file is already captured, so the agent loop can call
        this on every mutation without tracking what the checkpoint holds.
        A missing file is recorded with ``existed: False`` so restore()
        deletes it (reverting a file the agent created).
        """
        cp_dir = os.path.join(self._checkpoints_dir(), checkpoint_id)
        manifest_path = os.path.join(cp_dir, "manifest.json")
        if not os.path.isfile(manifest_path):
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        abs_path = os.path.abspath(file_path)
        try:
            rel_path = os.path.relpath(abs_path, self._root)
        except ValueError:
            rel_path = os.path.basename(abs_path)
        rel_norm = rel_path.replace("\\", "/")
        if any(item.get("relative") == rel_norm for item in manifest["files"]):
            return
        if os.path.isfile(abs_path):
            dest = os.path.join(cp_dir, rel_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(abs_path, dest)
            entry = {"original": abs_path.replace("\\", "/"), "relative": rel_norm,
                     "size": os.path.getsize(abs_path), "existed": True, "type": "file"}
        else:
            entry = {"original": abs_path.replace("\\", "/"), "relative": rel_norm,
                     "size": 0, "existed": False, "type": "missing"}
        manifest["files"].append(entry)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """List all available checkpoints."""
        checkpoints = []
        cp_base = self._checkpoints_dir()

        for entry in sorted(os.scandir(cp_base), key=lambda e: e.name, reverse=True):
            if not entry.is_dir():
                continue

            manifest_path = os.path.join(entry.path, "manifest.json")
            if os.path.isfile(manifest_path):
                try:
                    with open(manifest_path, "r") as f:
                        manifest = json.load(f)
                    checkpoints.append({
                        "id": manifest.get("id", entry.name),
                        "label": manifest.get("label", ""),
                        "created": manifest.get("created", 0),
                        "file_count": len(manifest.get("files", [])),
                    })
                except Exception:
                    pass

        return checkpoints

    def delete(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint. Returns True if the checkpoint existed and
        was removed, False if there was nothing to delete.
        """
        cp_dir = os.path.join(self._checkpoints_dir(), checkpoint_id)
        if not os.path.isdir(cp_dir):
            return False
        shutil.rmtree(cp_dir)
        return True

    def _cleanup(self) -> None:
        """Remove old checkpoints beyond the limit."""
        checkpoints = self.list_checkpoints()
        if len(checkpoints) > MAX_CHECKPOINTS:
            for cp in checkpoints[MAX_CHECKPOINTS:]:
                self.delete(cp["id"])
