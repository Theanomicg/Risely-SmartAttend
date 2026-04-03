from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.services.attendance import calculate_absence_duration_minutes, validate_active_attendance_transition, validate_attendance_transition  # noqa: E402
from app.services.attendance import calculate_current_alert_duration_minutes  # noqa: E402


class ValidateAttendanceTransitionTests(unittest.TestCase):
    def test_checkin_allows_first_event(self) -> None:
        decision = validate_attendance_transition("checkin", "class-10-a", None)
        self.assertTrue(decision.should_create_event)
        self.assertTrue(decision.success)
        self.assertEqual(decision.message, "Check-in successful.")

    def test_checkin_is_idempotent_for_same_class(self) -> None:
        latest_event = SimpleNamespace(event_type="checkin", classroom_id="class-10-a")
        decision = validate_attendance_transition("checkin", "class-10-a", latest_event)
        self.assertFalse(decision.should_create_event)
        self.assertTrue(decision.success)
        self.assertEqual(decision.message, "Student already checked in.")

    def test_checkin_rejects_conflicting_open_session(self) -> None:
        latest_event = SimpleNamespace(event_type="checkin", classroom_id="class-11-b")
        decision = validate_attendance_transition("checkin", "class-10-a", latest_event)
        self.assertFalse(decision.should_create_event)
        self.assertFalse(decision.success)
        self.assertIn("class-11-b", decision.message)

    def test_checkout_requires_open_session(self) -> None:
        decision = validate_attendance_transition("checkout", "class-10-a", None)
        self.assertFalse(decision.should_create_event)
        self.assertFalse(decision.success)
        self.assertEqual(decision.message, "Student is not currently checked in.")

    def test_checkout_rejects_wrong_class(self) -> None:
        latest_event = SimpleNamespace(event_type="checkin", classroom_id="class-11-b")
        decision = validate_attendance_transition("checkout", "class-10-a", latest_event)
        self.assertFalse(decision.should_create_event)
        self.assertFalse(decision.success)
        self.assertIn("class-11-b", decision.message)

    def test_checkout_allows_matching_open_session(self) -> None:
        latest_event = SimpleNamespace(event_type="checkin", classroom_id="class-10-a")
        decision = validate_attendance_transition("checkout", "class-10-a", latest_event)
        self.assertTrue(decision.should_create_event)
        self.assertTrue(decision.success)
        self.assertEqual(decision.message, "Check-out successful.")


class ValidateActiveAttendanceTransitionTests(unittest.TestCase):
    def test_checkin_allows_when_state_is_empty(self) -> None:
        decision = validate_active_attendance_transition("checkin", "class-10-a", None)
        self.assertTrue(decision.should_create_event)
        self.assertTrue(decision.success)
        self.assertEqual(decision.message, "Check-in successful.")

    def test_checkin_is_idempotent_for_same_class(self) -> None:
        active_session = SimpleNamespace(classroom_id="class-10-a")
        decision = validate_active_attendance_transition("checkin", "class-10-a", active_session)
        self.assertFalse(decision.should_create_event)
        self.assertTrue(decision.success)
        self.assertEqual(decision.message, "Student already checked in.")

    def test_checkout_rejects_wrong_class(self) -> None:
        active_session = SimpleNamespace(classroom_id="class-11-b")
        decision = validate_active_attendance_transition("checkout", "class-10-a", active_session)
        self.assertFalse(decision.should_create_event)
        self.assertFalse(decision.success)
        self.assertIn("class-11-b", decision.message)

    def test_checkout_allows_matching_open_session(self) -> None:
        active_session = SimpleNamespace(classroom_id="class-10-a")
        decision = validate_active_attendance_transition("checkout", "class-10-a", active_session)
        self.assertTrue(decision.should_create_event)
        self.assertTrue(decision.success)
        self.assertEqual(decision.message, "Check-out successful.")


class CalculateAbsenceDurationTests(unittest.TestCase):
    def test_no_alert_before_threshold_when_student_has_never_been_seen(self) -> None:
        now = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)
        checked_in_at = now - timedelta(minutes=10)
        duration = calculate_absence_duration_minutes(
            checked_in_at=checked_in_at,
            last_seen_at=None,
            now=now,
            threshold_minutes=15,
        )
        self.assertIsNone(duration)

    def test_alert_starts_from_checkin_when_student_has_never_been_seen(self) -> None:
        now = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)
        checked_in_at = now - timedelta(minutes=17)
        duration = calculate_absence_duration_minutes(
            checked_in_at=checked_in_at,
            last_seen_at=None,
            now=now,
            threshold_minutes=15,
        )
        self.assertEqual(duration, 17)

    def test_alert_starts_from_last_seen_when_student_was_detected(self) -> None:
        now = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)
        checked_in_at = now - timedelta(minutes=40)
        last_seen_at = now - timedelta(minutes=18)
        duration = calculate_absence_duration_minutes(
            checked_in_at=checked_in_at,
            last_seen_at=last_seen_at,
            now=now,
            threshold_minutes=15,
        )
        self.assertEqual(duration, 18)

    def test_camera_recovery_delays_alert_until_monitoring_is_healthy(self) -> None:
        now = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)
        checked_in_at = now - timedelta(minutes=40)
        last_seen_at = now - timedelta(minutes=30)
        monitoring_active_since = now - timedelta(minutes=5)
        duration = calculate_absence_duration_minutes(
            checked_in_at=checked_in_at,
            last_seen_at=last_seen_at,
            now=now,
            threshold_minutes=15,
            monitoring_active_since=monitoring_active_since,
        )
        self.assertIsNone(duration)


class CalculateCurrentAlertDurationTests(unittest.TestCase):
    def test_duration_grows_from_absent_since_at(self) -> None:
        now = datetime(2026, 4, 2, 12, 20, tzinfo=timezone.utc)
        created_at = now - timedelta(minutes=2)
        duration = calculate_current_alert_duration_minutes(
            created_at=created_at,
            payload={
                "duration_minutes": 15,
                "absent_since_at": (now - timedelta(minutes=20)).isoformat(),
            },
            now=now,
        )
        self.assertEqual(duration, 20)

    def test_legacy_alert_duration_uses_creation_time_fallback(self) -> None:
        now = datetime(2026, 4, 2, 12, 20, tzinfo=timezone.utc)
        created_at = now - timedelta(minutes=3)
        duration = calculate_current_alert_duration_minutes(
            created_at=created_at,
            payload={"duration_minutes": 15},
            now=now,
        )
        self.assertEqual(duration, 18)


if __name__ == "__main__":
    unittest.main()
