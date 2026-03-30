from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AttendanceEvent, CameraConfig, DetectionEvent, MonitoringConfig, Student


settings = get_settings()


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


async def list_active_students(session: AsyncSession, classroom_id: str | None = None) -> list[dict]:
    latest_subquery = (
        select(
            AttendanceEvent.uid,
            AttendanceEvent.classroom_id,
            AttendanceEvent.event_type,
            AttendanceEvent.timestamp,
        )
        .distinct(AttendanceEvent.uid)
        .order_by(AttendanceEvent.uid, desc(AttendanceEvent.timestamp))
        .subquery()
    )

    query = (
        select(
            latest_subquery.c.uid,
            latest_subquery.c.classroom_id,
            latest_subquery.c.timestamp,
            Student,
        )
        .join(Student, Student.uid == latest_subquery.c.uid)
        .where(latest_subquery.c.event_type == "checkin")
    )
    if classroom_id:
        query = query.where(latest_subquery.c.classroom_id == classroom_id)

    rows = (await session.execute(query)).all()
    active_students: list[dict] = []
    for row in rows:
        uid, latest_classroom_id, checked_in_at, student = row
        last_seen_query = (
            select(DetectionEvent.timestamp)
            .where(
                and_(
                    DetectionEvent.uid == uid,
                    DetectionEvent.classroom_id == latest_classroom_id,
                )
            )
            .order_by(desc(DetectionEvent.timestamp))
            .limit(1)
        )
        last_seen = (await session.execute(last_seen_query)).scalar_one_or_none()
        active_students.append(
            {
                "uid": student.uid,
                "name": student.name,
                "class_id": student.class_id,
                "classroom_id": latest_classroom_id,
                "checked_in_at": checked_in_at,
                "last_seen_at": last_seen,
            }
        )
    return active_students


async def get_enabled_cameras(session: AsyncSession) -> list[CameraConfig]:
    result = await session.execute(select(CameraConfig).where(CameraConfig.enabled.is_(True)))
    return list(result.scalars().all())


async def list_attendance_sessions(
    session: AsyncSession,
    classroom_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query = (
        select(AttendanceEvent, Student)
        .join(Student, Student.uid == AttendanceEvent.uid)
        .order_by(AttendanceEvent.timestamp.asc(), AttendanceEvent.id.asc())
    )
    if classroom_id:
        query = query.where(AttendanceEvent.classroom_id == classroom_id)

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
                "class_id": student.class_id,
                "classroom_id": event.classroom_id,
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
                        "class_id": student.class_id,
                        "classroom_id": event.classroom_id,
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
