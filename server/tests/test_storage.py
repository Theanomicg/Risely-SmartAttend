from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app import storage  # noqa: E402


class StudentStorageTests(unittest.TestCase):
    def test_delete_student_photo_dir_removes_saved_files(self) -> None:
        original_dir = storage.settings.enrollment_photo_dir
        temp_dir = tempfile.mkdtemp(prefix="smartattend-storage-")
        try:
            storage.settings.enrollment_photo_dir = temp_dir
            relative_path = storage.save_student_photo("student-1", "photo.jpg", b"123")
            self.assertTrue((Path(temp_dir) / relative_path).exists())

            storage.delete_student_photo_dir("student-1")

            self.assertFalse(storage.student_photo_dir("student-1").exists())
        finally:
            storage.settings.enrollment_photo_dir = original_dir
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
