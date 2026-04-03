from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


KIOSK_DIR = Path(__file__).resolve().parents[1]
if str(KIOSK_DIR) not in sys.path:
    sys.path.insert(0, str(KIOSK_DIR))

from main import KioskConfig, SmartAttendKiosk  # noqa: E402


class KioskAutoActionTests(unittest.TestCase):
    def _build_kiosk(self, action: str = "auto") -> SmartAttendKiosk:
        with patch("main.cv2.VideoCapture") as video_capture:
            capture = Mock()
            capture.read.return_value = (False, None)
            video_capture.return_value = capture
            return SmartAttendKiosk(
                KioskConfig(
                    api_url="http://127.0.0.1:8010",
                    class_id="Grade-10-A",
                    device_id="test-kiosk",
                    camera_source="",
                    camera_index=1,
                    camera_backend="dshow",
                    action=action,
                    face_model="ArcFace",
                    embedding_dim=128,
                )
            )

    def test_auto_action_falls_back_to_checkout_for_repeat_scan(self) -> None:
        kiosk = self._build_kiosk(action="auto")
        kiosk._post_action = Mock(side_effect=[
            {
                "success": True,
                "message": "Student already checked in.",
                "student_name": "Nikchaya Lamsal",
            },
            {
                "success": True,
                "message": "Check-out successful.",
                "student_name": "Nikchaya Lamsal",
            },
        ])

        result = kiosk.submit_attendance([0.0] * 128)

        self.assertEqual(kiosk._post_action.call_args_list[0].args[0], "checkin")
        self.assertEqual(kiosk._post_action.call_args_list[1].args[0], "checkout")
        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "Check-out successful.")

    def test_auto_action_keeps_first_checkin_result_when_not_repeat_scan(self) -> None:
        kiosk = self._build_kiosk(action="auto")
        kiosk._post_action = Mock(return_value={
            "success": True,
            "message": "Check-in successful.",
            "student_name": "Nikchaya Lamsal",
        })

        result = kiosk.submit_attendance([0.0] * 128)

        kiosk._post_action.assert_called_once()
        self.assertEqual(kiosk._post_action.call_args.args[0], "checkin")
        self.assertEqual(result["message"], "Check-in successful.")


if __name__ == "__main__":
    unittest.main()
