from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import ActiveAttendanceSession, Alert, AttendanceEvent, CameraConfig, DetectionEvent, MonitoringConfig, Student


settings = get_settings()


@dataclass(frozen=True)
class AttendanceDecision:
    should_create_event: bool
    success: bool
    message: str


def _validate_attendance_transition_from_open_classroom(
    action: str,
    requested_class_id: str,
    open_classroom_id: str | None,
) -> AttendanceDecision:
    if action not in {"checkin", "checkout"}:
        return AttendanceDecision(False, False, f"Unsupported attendance action: {action}.")

    if action == "checkin":
        if open_classroom_id is None:
            return AttendanceDecision(True, True, "Check-in successful.")
        if open_classroom_id == requested_class_id:
            return AttendanceDecision(False, True, "Student already checked in.")
        return AttendanceDecision(False, False, f"Student is already checked in to {open_classroom_id}.")

    if open_classroom_id is None:
        return AttendanceDecision(False, False, "Student is not currently checked in.")
    if open_classroom_id != requested_class_id:
        return AttendanceDecision(
            False,
            False,
            f"Student is checked in to {open_classroom_id}, not {requested_class_id}.",
        )
    return AttendanceDecision(True, True, "Check-out successful.")


def validate_attendance_transition(
    action: str,
    requested_class_id: str,
    latest_event: AttendanceEvent | None,
) -> AttendanceDecision:
    open_classroom_id = None
    if latest_event and latest_event.event_type == "checkin":
        open_classroom_id = latest_event.classroom_id
    return _validate_attendance_transition_from_open_classroom(action, requested_class_id, open_classroom_id)


def validate_active_attendance_transition(
    action: str,
    requested_class_id: str,
    active_session: ActiveAttendanceSession | None,
) -> AttendanceDecision:
    return _validate_attendance_transition_from_open_classroom(
        action,
        requested_class_id,
        active_session.classroom_id if active_session else None,
    )


def build_latest_attendance_event_subquery():
    ranked_attendance = (
        select(
            AttendanceEvent.uid.label("uid"),
            AttendanceEvent.classroom_id.label("classroom_id"),
            AttendanceEvent.event_type.label("event_type"),
            AttendanceEvent.timestamp.label("timestamp"),
            func.row_number()
            .over(
                partition_by=AttendanceEvent.uid,
                order_by=[AttendanceEvent.timestamp.desc(), AttendanceEvent.id.desc()],
            )
            .label("row_number"),
        )
        .subquery()
    )

    return (
        select(
            ranked_attendance.c.uid,
            ranked_attendance.c.classroom_id,
            ranked_attendance.c.event_type,
            ranked_attendance.c.timestamp,
        )
        .where(ranked_attendance.c.row_number == 1)
        .subquery()
    )


def calculate_absence_duration_minutes(
    *,
    checked_in_at: datetime,
    last_seen_at: datetime | None,
    now: datetime,
    threshold_minutes: int,
    monitoring_active_since: datetime | None = None,
) -> int | None:
    reference_time = last_seen_at or checked_in_at
    if monitoring_active_since and monitoring_active_since > reference_time:
        reference_time = monitoring_active_since
    elapsed = now - reference_time
    threshold = timedelta(minutes=threshold_minutes)
    if elapsed < threshold:
        return None

    return max(threshold_minutes, int(elapsed.total_seconds() // 60))


def calculate_current_alert_duration_minutes(
    *,
    created_at: datetime,
    payload: dict[str, Any],
    now: datetime,
) -> int:
    base_duration = max(int(payload.get("duration_minutes", 0)), 0)
    absent_since_raw = payload.get("absent_since_at") or payload.get("last_seen_at")

    absent_since_at: datetime | None = None
    if absent_since_raw:
        try:
            absent_since_at = datetime.fromisoformat(absent_since_raw)
        except ValueError:
            absent_since_at = None
    elif base_duration:
        absent_since_at = created_at - timedelta(minutes=base_duration)

    if absent_since_at is None:
        return base_duration

    elapsed_minutes = int((now - absent_since_at).total_seconds() // 60)
    return max(base_duration, elapsed_minutes, 0)


async def ensure_default_monitoring_config(session: AsyncSession) -> MonitoringConfig:
    config = await session.get(MonitoringConfig, 1)
    if config:
        return config

    config = MonitoringConfig(
        id=1,
        monitoring_interval_minutes=settings.monitoring_interval_minutes,
        absence_alert_threshold_minutes=settings.absence_alert_threshold_minutes,
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


async def rebuild_active_attendance_state(session: AsyncSession) -> int:
    latest_subquery = build_latest_attendance_event_subquery()
    rows = (
        await session.execute(
            select(
                latest_subquery.c.uid,
                latest_subquery.c.classroom_id,
                latest_subquery.c.timestamp,
            ).where(latest_subquery.c.event_type == "checkin")
        )
    ).all()

    await session.execute(delete(ActiveAttendanceSession))
    for uid, classroom_id, checked_in_at in rows:
        session.add(
            ActiveAttendanceSession(
                uid=uid,
                classroom_id=classroom_id,
                checked_in_at=checked_in_at,
            )
        )
    return len(rows)


async def list_active_students(session: AsyncSession, class_id: str | None = None) -> list[dict]:
    last_seen_subquery = (
        select(
            DetectionEvent.uid,
            DetectionEvent.classroom_id,
            func.max(DetectionEvent.timestamp).label("last_seen_at"),
        )
        .group_by(DetectionEvent.uid, DetectionEvent.classroom_id)
        .subquery()
    )

    query = (
        select(
            ActiveAttendanceSession.uid,
            ActiveAttendanceSession.classroom_id,
            ActiveAttendanceSession.checked_in_at,
            Student,
            last_seen_subquery.c.last_seen_at,
        )
        .join(Student, Student.uid == ActiveAttendanceSession.uid)
        .outerjoin(
            last_seen_subquery,
            (last_seen_subquery.c.uid == ActiveAttendanceSession.uid)
            & (last_seen_subquery.c.classroom_id == ActiveAttendanceSession.classroom_id),
        )
    )
    if class_id:
        query = query.where(ActiveAttendanceSession.classroom_id == class_id)

    rows = (await session.execute(query)).all()
    active_students: list[dict] = []
    for row in rows:
        _uid, latest_classroom_id, checked_in_at, student, last_seen = row
        active_students.append(
            {
                "uid": student.uid,
                "name": student.name,
                "class_id": latest_classroom_id,
                "checked_in_at": checked_in_at,
                "last_seen_at": last_seen,
            }
        )
    return active_students


async def get_enabled_cameras(session: AsyncSession) -> list[CameraConfig]:
    result = await session.execute(select(CameraConfig).where(CameraConfig.enabled.is_(True)))
    return list(result.scalars().all())


async def get_active_attendance_session(session: AsyncSession, uid: str) -> ActiveAttendanceSession | None:
    return await session.get(ActiveAttendanceSession, uid)


async def get_latest_attendance_event(session: AsyncSession, uid: str) -> AttendanceEvent | None:
    query = (
        select(AttendanceEvent)
        .where(AttendanceEvent.uid == uid)
        .order_by(AttendanceEvent.timestamp.desc(), AttendanceEvent.id.desc())
        .limit(1)
    )
    return await session.scalar(query)


async def resolve_active_alerts(
    session: AsyncSession,
    *,
    uid: str,
    class_id: str,
    resolved_at: datetime | None = None,
) -> list[Alert]:
    alerts = list(
        (
            await session.scalars(
                select(Alert).where(
                    and_(
                        Alert.uid == uid,
                        Alert.classroom_id == class_id,
                        Alert.status == "active",
                    )
                )
            )
        ).all()
    )
    if not alerts:
        return []

    resolved_timestamp = resolved_at or now_utc()
    for alert in alerts:
        alert.status = "resolved"
        alert.acknowledged_at = resolved_timestamp
    return alerts


async def list_attendance_sessions(
    session: AsyncSession,
    class_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query = (
        select(AttendanceEvent, Student)
        .join(Student, Student.uid == AttendanceEvent.uid)
        .order_by(AttendanceEvent.timestamp.asc(), AttendanceEvent.id.asc())
    )
    if class_id:
        query = query.where(AttendanceEvent.classroom_id == class_id)

    rows = (await session.execute(query)).all()
    sessions_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    completed_sessions: list[dict[str, Any]] = []

    for event, student in rows:
        key = (event.uid, event.classroom_id)
        open_session = sessions_by_key.get(key)

        if event.event_type == "checkin":
            if open_session:
                completed_sessions.append(open_session)
            sessions_by_key[key] = {
                "uid": student.uid,
                "name": student.name,
                "class_id": event.classroom_id,
                "checked_in_at": event.timestamp,
                "checked_out_at": None,
                "status": "checked_in",
            }
            continue

        if event.event_type == "checkout":
            if open_session:
                open_session["checked_out_at"] = event.timestamp
                open_session["status"] = "checked_out"
                completed_sessions.append(open_session)
                del sessions_by_key[key]
            else:
                completed_sessions.append(
                    {
                        "uid": student.uid,
                        "name": student.name,
                        "class_id": event.classroom_id,
                        "checked_in_at": None,
                        "checked_out_at": event.timestamp,
                        "status": "checked_out",
                    }
                )

    completed_sessions.extend(sessions_by_key.values())
    completed_sessions.sort(
        key=lambda item: item["checked_in_at"] or item["checked_out_at"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return completed_sessions[:limit]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
