# Validated multimodal image inputs for the agent runtime.

from __future__ import annotations

import base64
import binascii
import os
import re
from typing import Any

MAX_IMAGE_COUNT = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_MIME_TYPES = frozenset({
    "image/png", "image/jpeg", "image/webp", "image/gif",
})
_DATA_URL_RE = re.compile(
    r"^data:(image/(?:png|jpeg|webp|gif));base64,([A-Za-z0-9+/=]+)$",
    re.IGNORECASE,
)


def _matches_signature(mime_type: str, data: bytes) -> bool:
    if mime_type == "image/png":
        return data.startswith(bytes.fromhex("89504e470d0a1a0a"))
    if mime_type == "image/jpeg":
        return data.startswith(bytes.fromhex("ffd8ff"))
    if mime_type == "image/gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if mime_type == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def validate_image_attachments(value: Any) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError("Image attachments must be a list")
    if len(value) > MAX_IMAGE_COUNT:
        raise ValueError(f"Attach at most {MAX_IMAGE_COUNT} images per prompt")

    normalized: list[dict[str, Any]] = []
    total_bytes = 0
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"Image attachment {index + 1} is invalid")
        data_url = str(item.get("data_url") or item.get("dataUrl") or "")
        match = _DATA_URL_RE.fullmatch(data_url)
        if not match:
            raise ValueError(
                "Only PNG, JPEG, WebP, and GIF image attachments are supported")
        mime_type = match.group(1).lower()
        try:
            data = base64.b64decode(match.group(2), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError(
                f"Image attachment {index + 1} is not valid base64") from exc
        size = len(data)
        if not size:
            raise ValueError(f"Image attachment {index + 1} is empty")
        if size > MAX_IMAGE_BYTES:
            raise ValueError("Each image must be 5 MB or smaller")
        if not _matches_signature(mime_type, data):
            raise ValueError(
                f"Image attachment {index + 1} does not match its declared type")
        total_bytes += size
        if total_bytes > MAX_TOTAL_IMAGE_BYTES:
            raise ValueError("Image attachments must total 10 MB or less")

        raw_name = str(item.get("name") or f"image-{index + 1}")
        name = os.path.basename(raw_name.replace(chr(92), "/"))[:128]
        normalized.append({
            "id": str(item.get("id") or f"image-{index + 1}")[:80],
            "name": name or f"image-{index + 1}",
            "mime_type": mime_type,
            "size": size,
            "data_url": data_url,
        })
    return normalized


def attachment_metadata(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or "image"),
        "mime_type": str(item.get("mime_type") or "image/unknown"),
        "size": int(item.get("size") or 0),
    } for item in attachments]


def build_user_content(
    text: str,
    attachments: list[dict[str, Any]],
) -> str | list[dict[str, Any]]:
    if not attachments:
        return text
    names = ", ".join(str(item.get("name") or "image") for item in attachments)
    parts: list[dict[str, Any]] = [{
        "type": "text",
        "text": f"{text}\n\nAttached images: {names}",
    }]
    parts.extend({
        "type": "image_url",
        "image_url": {"url": str(item["data_url"]), "detail": "high"},
    } for item in attachments)
    return parts


def persistence_safe_content(content: Any) -> Any:
    if not isinstance(content, list):
        return content
    text_parts: list[str] = []
    image_count = 0
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text" and part.get("text"):
            text_parts.append(str(part["text"]))
        elif part.get("type") in {"image_url", "input_image"}:
            image_count += 1
    if image_count:
        text_parts.append(
            f"[{image_count} image attachment{'s' if image_count != 1 else ''} "
            "omitted from saved transcript]"
        )
    return "\n\n".join(text_parts).strip()


def messages_for_persistence(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for message in messages:
        item = {
            key: value for key, value in message.items()
            if not str(key).startswith("_")
        }
        item["content"] = persistence_safe_content(item.get("content"))
        safe.append(item)
    return safe
