from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from app.config import get_settings


settings = get_settings()
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def ensure_storage_dirs() -> None:
    settings.enrollment_photo_path.mkdir(parents=True, exist_ok=True)


def student_photo_dir(uid: str) -> Path:
    safe_uid = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in uid)
    return settings.enrollment_photo_path / safe_uid


def save_student_photo(uid: str, original_filename: str, content: bytes) -> str:
    target_dir = student_photo_dir(uid)
    target_dir.mkdir(parents=True, exist_ok=True)

    extension = Path(original_filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        extension = ".jpg"

    filename = f"{uuid4().hex}{extension}"
    file_path = target_dir / filename
    file_path.write_bytes(content)
    return str(file_path.relative_to(settings.enrollment_photo_path)).replace("\\", "/")


def resolve_student_photo(relative_path: str) -> Path:
    base_path = settings.enrollment_photo_path.resolve()
    file_path = (base_path / relative_path).resolve()
    if base_path not in file_path.parents and file_path != base_path:
        raise ValueError("Invalid photo path.")
    return file_path


def delete_student_photo_dir(uid: str) -> None:
    base_path = settings.enrollment_photo_path.resolve()
    target_dir = student_photo_dir(uid).resolve()
    if base_path not in target_dir.parents:
        raise ValueError("Invalid student photo directory.")
    if target_dir.exists():
        shutil.rmtree(target_dir)
