"""PatchGenerator — parses AI output into diffs and applies patches."""

import os
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)


class PatchGenerator:
    """Parses AI-generated code changes and applies them to the filesystem."""

    def __init__(self, project_root: str | None = None) -> None:
        self._project_root = os.path.abspath(project_root) if project_root else None

    def _resolve_patch_path(self, file_path: str) -> str:
        """Resolve an AI-provided patch path inside the active project root."""
        if not file_path:
            raise ValueError("Patch has no file path")
        if file_path in {"/dev/null", "NUL"}:
            raise ValueError("Patch target cannot be a null device")

        normalized = file_path.replace("\\", os.sep).replace("/", os.sep)
        if self._project_root and not os.path.isabs(normalized):
            abs_path = os.path.abspath(os.path.join(self._project_root, normalized))
        else:
            abs_path = os.path.abspath(normalized)

        if self._project_root:
            try:
                common = os.path.commonpath([self._project_root, abs_path])
            except ValueError as exc:
                raise PermissionError("Patch target is outside the active project") from exc
            if common != self._project_root:
                raise PermissionError("Patch target is outside the active project")

        return abs_path

    def parse_response(self, response: str) -> list[dict[str, Any]]:
        """Parse an AI response for code blocks and diff blocks.

        Returns a list of patch objects:
        {
            "file": "path/to/file",
            "action": "modify" | "create" | "delete",
            "content": "full file content or diff",
            "language": "python",
        }
        """
        patches: list[dict[str, Any]] = []

        # Pattern: ```diff or ```language with file path header
        # Look for patterns like:
        #   ## File: path/to/file
        #   ```python
        #   content
        #   ```
        pattern = re.compile(
            r'(?:#{1,3}\s*(?:File|Modify|Create|New File|Edit):\s*`?([^\n`]+)`?\s*\n)?'
            r'```(\w+)?\n(.*?)```',
            re.DOTALL,
        )

        for match in pattern.finditer(response):
            file_path = match.group(1)
            language = match.group(2) or ""
            content = match.group(3).rstrip("\n")

            if language == "diff":
                # Parse unified diff
                diff_patches = self._parse_diff(content)
                patches.extend(diff_patches)
            elif file_path:
                patches.append({
                    "file": file_path.strip(),
                    "action": "create" if "create" in response[:match.start()].lower().split("\n")[-1] else "modify",
                    "content": content,
                    "language": language,
                })

        return patches

    def _parse_diff(self, diff_text: str) -> list[dict[str, Any]]:
        """Parse a unified diff into patch objects."""
        patches: list[dict[str, Any]] = []
        current_file = None
        current_lines: list[str] = []

        for line in diff_text.split("\n"):
            if line.startswith("--- "):
                # Save previous file
                if current_file and current_lines:
                    patches.append({
                        "file": current_file,
                        "action": "modify",
                        "diff": "\n".join(current_lines),
                        "language": "diff",
                    })
                current_lines = [line]
                # Extract file path (--- a/path/to/file)
                path = line[4:].strip()
                if path.startswith("a/"):
                    path = path[2:]
                current_file = path

            elif line.startswith("+++ "):
                current_lines.append(line)
                # The +++ line has the "new" file path
                path = line[4:].strip()
                if path.startswith("b/"):
                    path = path[2:]
                if path != "/dev/null":
                    current_file = path

            elif line.startswith("@@") or line.startswith("+") or line.startswith("-") or line.startswith(" "):
                current_lines.append(line)

        # Save last file
        if current_file and current_lines:
            patches.append({
                "file": current_file,
                "action": "modify",
                "diff": "\n".join(current_lines),
                "language": "diff",
            })

        return patches

    def apply_patch(self, patch: dict[str, Any]) -> None:
        """Apply a single patch to the filesystem."""
        file_path = patch.get("file", "")
        action = patch.get("action", "modify")

        abs_path = self._resolve_patch_path(file_path)

        if action == "mkdir":
            os.makedirs(abs_path, exist_ok=True)
            return

        if action == "rmdir":
            if os.path.isdir(abs_path):
                os.rmdir(abs_path)
            return

        if action == "move":
            source_path = self._resolve_patch_path(str(patch.get("source") or ""))
            if not os.path.isfile(source_path):
                raise FileNotFoundError(f"Move source not found: {patch.get('source')}")
            if os.path.exists(abs_path):
                raise FileExistsError(f"Move destination already exists: {file_path}")
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            content = patch.get("content")
            if isinstance(content, str):
                temp_path = abs_path + ".nexcoder_tmp"
                with open(temp_path, "w", encoding="utf-8") as handle:
                    handle.write(content)
                os.replace(temp_path, abs_path)
                os.unlink(source_path)
            else:
                os.replace(source_path, abs_path)
            return

        if action == "delete":
            if os.path.exists(abs_path):
                os.unlink(abs_path)
            return

        if action == "create" or (action == "modify" and "content" in patch):
            # Full file replacement
            content = patch.get("content", "")
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            return

        if "diff" in patch:
            # Apply unified diff (basic line-level application)
            self._apply_unified_diff(abs_path, patch["diff"])

    def _apply_unified_diff(self, file_path: str, diff_text: str) -> None:
        """Apply a unified diff to a file (basic implementation)."""
        if not os.path.isfile(file_path):
            logger.warning(f"Cannot apply diff — file not found: {file_path}")
            return

        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Parse hunks
        hunk_pattern = re.compile(r"@@ -(\d+),?\d* \+(\d+),?\d* @@")
        output_lines = list(lines)
        offset = 0

        current_line = 0
        for diff_line in diff_text.split("\n"):
            hunk_match = hunk_pattern.match(diff_line)
            if hunk_match:
                current_line = int(hunk_match.group(1)) - 1 + offset
                continue

            if diff_line.startswith("-"):
                # Remove line
                if 0 <= current_line < len(output_lines):
                    output_lines.pop(current_line)
                    offset -= 1
            elif diff_line.startswith("+"):
                # Add line
                new_line = diff_line[1:] + "\n"
                output_lines.insert(current_line, new_line)
                current_line += 1
                offset += 1
            elif diff_line.startswith(" "):
                current_line += 1

        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(output_lines)

    def generate_diff(self, original: str, modified: str, file_path: str) -> str:
        """Generate a unified diff between original and modified content."""
        import difflib

        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )

        return "\n".join(diff)

    def _apply_unified_diff_to_text(self, original_text: str, diff_text: str) -> str:
        """Apply a unified diff to a text string and return the modified text.

        This mirrors _apply_unified_diff but operates in-memory and returns
        the updated content rather than writing to disk.
        """
        lines = original_text.splitlines(keepends=True)

        hunk_pattern = re.compile(r"@@ -(?P<old_start>\d+),?\d* \+(?P<new_start>\d+),?\d* @@")
        output_lines = list(lines)
        offset = 0

        current_line = 0
        for diff_line in diff_text.split("\n"):
            hunk_match = hunk_pattern.match(diff_line)
            if hunk_match:
                current_line = int(hunk_match.group("old_start")) - 1 + offset
                continue

            if diff_line.startswith("-"):
                if 0 <= current_line < len(output_lines):
                    output_lines.pop(current_line)
                    offset -= 1
            elif diff_line.startswith("+"):
                new_line = diff_line[1:] + "\n"
                output_lines.insert(current_line, new_line)
                current_line += 1
                offset += 1
            elif diff_line.startswith(" "):
                current_line += 1

        return "".join(output_lines)

    def apply_patchset(self, patches: list[dict[str, Any]]) -> None:
        """Apply a set of patches atomically.

        The method writes modified/new files to temporary files and then
        replaces originals using os.replace to minimize half-applied states.
        Deletions are performed after successful replaces. This method does
        not create checkpoints — the caller should create a checkpoint
        before calling this when rollback is desired.
        """
        # Resolve absolute paths and prepare operations
        ops: list[dict[str, Any]] = []
        deletes: list[str] = []
        directories_to_create: list[str] = []
        directories_to_remove: list[str] = []

        for patch in patches:
            file_path = patch.get("file", "")
            abs_path = self._resolve_patch_path(file_path)
            action = patch.get("action", "modify")

            if action == "mkdir":
                directories_to_create.append(abs_path)
                continue

            if action == "rmdir":
                directories_to_remove.append(abs_path)
                continue

            if action == "delete":
                deletes.append(abs_path)
                continue

            if action == "move":
                source_path = self._resolve_patch_path(str(patch.get("source") or ""))
                if not os.path.isfile(source_path):
                    raise FileNotFoundError(f"Move source not found: {patch.get('source')}")
                if os.path.exists(abs_path):
                    raise FileExistsError(f"Move destination already exists: {file_path}")
                if "content" not in patch and "diff" not in patch:
                    ops.append({"source": source_path, "target": abs_path, "direct_move": True})
                    continue
                deletes.append(source_path)

            # For create/modify: compute temp file path
            dirpath = os.path.dirname(abs_path)
            os.makedirs(dirpath, exist_ok=True)
            temp_path = abs_path + ".nexcoder_tmp"

            if "content" in patch:
                content = patch.get("content", "")
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(content)
                ops.append({"temp": temp_path, "target": abs_path})
            elif "diff" in patch:
                if not os.path.isfile(abs_path):
                    # Can't apply diff to missing file — write diff as new file
                    new_text = self._apply_unified_diff_to_text("", patch["diff"])
                else:
                    with open(abs_path, "r", encoding="utf-8") as f:
                        orig = f.read()
                    new_text = self._apply_unified_diff_to_text(orig, patch["diff"])

                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(new_text)
                ops.append({"temp": temp_path, "target": abs_path})
            else:
                # Unknown patch format — skip
                logger.warning(f"Skipping unsupported patch for {abs_path}")

        for directory in sorted(set(directories_to_create), key=len):
            os.makedirs(directory, exist_ok=True)

        # Perform atomic replace operations
        for op in ops:
            try:
                if op.get("direct_move"):
                    os.makedirs(os.path.dirname(op["target"]), exist_ok=True)
                    os.replace(op["source"], op["target"])
                else:
                    os.replace(op["temp"], op["target"])
            except Exception as e:
                logger.error(f"Failed to apply patch to {op['target']}: {e}")
                # Attempt best-effort cleanup of temp files
                try:
                    if op.get("temp") and os.path.exists(op["temp"]):
                        os.unlink(op["temp"])
                except Exception:
                    pass
                raise

        # Perform deletions after all replaces succeeded
        for p in deletes:
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except Exception as e:
                logger.error(f"Failed to delete {p} during patchset apply: {e}")
                raise

        for directory in sorted(set(directories_to_remove), key=len, reverse=True):
            if os.path.isdir(directory):
                os.rmdir(directory)
