"""Save uploaded files to ./uploads with safe, unique names."""
import os
import uuid
from datetime import datetime

from fastapi import UploadFile, HTTPException

UPLOAD_DIR = "uploads"
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".heic"}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def save_upload(file: UploadFile | None, subdir: str = "misc") -> str | None:
    """Returns the relative path stored in DB, or None if no file."""
    if not file or not file.filename:
        return None

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"不支持的文件类型：{ext}（仅支持图片/PDF）")

    blob = file.file.read(MAX_BYTES + 1)
    if len(blob) > MAX_BYTES:
        raise HTTPException(400, "文件超过 10MB 上限")
    if len(blob) == 0:
        return None

    today = datetime.utcnow().strftime("%Y%m")
    folder = os.path.join(UPLOAD_DIR, subdir, today)
    os.makedirs(folder, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(folder, safe_name)
    with open(path, "wb") as f:
        f.write(blob)
    return path  # e.g. uploads/requests/202606/abc123.png
