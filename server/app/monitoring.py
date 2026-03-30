from __future__ import annotations

from datetime import timedelta

import cv2
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.face import cosine_similarity, extract_embeddings_from_image
from app.models import Alert, AttendanceEvent, DetectionEvent, Student
from app.services.attendance import ensure_default_monitoring_config, get_enabled_cameras, now_utc
from app.ws import manager


class MonitoringService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory
        self.scheduler = AsyncIOScheduler()
        self._last_run = None

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.add_job(self.run_cycle, "interval", minutes=1, id="monitoring-loop")
            self.scheduler.start()

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def run_cycle(self) -> None:
        async with self.session_factory() as session:
            config = await ensure_default_monitoring_config(session)
            now = now_utc()
            if self._last_run and now - self._last_run < timedelta(minutes=config.monitoring_interval_minutes):
                return
            self._last_run = now

            cameras = await get_enabled_cameras(session)
            active_students = await self._get_active_students(session)
            active_by_classroom: dict[str, list[Student]] = {}
            for classroom_id, student in active_students:
                active_by_classroom.setdefault(classroom_id, []).append(student)

            for camera in cameras:
                students = active_by_classroom.get(camera.classroom_id, [])
                if not students:
                    continue
                frame = self._capture_frame(camera.rtsp_url)
                if frame is None:
                    continue
                try:
                    observed_embeddings = extract_embeddings_from_image(frame)
                except Exception:
                    continue
                await self._record_matches(session, camera.classroom_id, students, observed_embeddings)

            await self._raise_absence_alerts(session, config.absence_alert_threshold_minutes)
            await session.commit()

    def _capture_frame(self, rtsp_url: str):
        capture = cv2.VideoCapture(rtsp_url)
        ok, frame = capture.read()
        capture.release()
        return frame if ok else None

    async def _get_active_students(self, session: AsyncSession) -> list[tuple[str, Student]]:
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
            select(latest_subquery.c.classroom_id, Student)
            .join(Student, Student.uid == latest_subquery.c.uid)
            .where(latest_subquery.c.event_type == "checkin")
        )
        rows = (await session.execute(query)).all()
        return [(row[0], row[1]) for row in rows]

    async def _record_matches(
        self,
        session: AsyncSession,
        classroom_id: str,
        students: list[Student],
        observed_embeddings: list[list[float]],
    ) -> None:
        for student in students:
            best_confidence = 0.0
            for observed_embedding in observed_embeddings:
                for stored in student.face_embeddings:
                    confidence = cosine_similarity(stored, observed_embedding)
                    if confidence > best_confidence:
                        best_confidence = confidence
            if best_confidence >= 0.70:
                session.add(
                    DetectionEvent(
                        uid=student.uid,
                        classroom_id=classroom_id,
                        confidence=best_confidence,
                    )
                )
                active_alert = await session.scalar(
                    select(Alert).where(
                        and_(
                            Alert.uid == student.uid,
                            Alert.classroom_id == classroom_id,
                            Alert.status == "active",
                        )
                    )
                )
                if active_alert:
                    active_alert.status = "resolved"
                    active_alert.acknowledged_at = now_utc()

    async def _raise_absence_alerts(self, session: AsyncSession, threshold_minutes: int) -> None:
        active_students = await self._get_active_students(session)
        now = now_utc()
        threshold = timedelta(minutes=threshold_minutes)

        for classroom_id, student in active_students:
            last_seen = await session.scalar(
                select(DetectionEvent.timestamp)
                .where(
                    and_(
                        DetectionEvent.uid == student.uid,
                        DetectionEvent.classroom_id == classroom_id,
                    )
                )
                .order_by(desc(DetectionEvent.timestamp))
                .limit(1)
            )

            if last_seen and now - last_seen < threshold:
                continue

            existing = await session.scalar(
                select(Alert).where(
                    and_(
                        Alert.uid == student.uid,
                        Alert.classroom_id == classroom_id,
                        Alert.status == "active",
                    )
                )
            )
            if existing:
                continue

            duration_minutes = threshold_minutes if last_seen is None else int((now - last_seen).total_seconds() // 60)
            alert = Alert(
                uid=student.uid,
                classroom_id=classroom_id,
                status="active",
                payload={
                    "student_name": student.name,
                    "duration_minutes": duration_minutes,
                    "last_seen_at": last_seen.isoformat() if last_seen else None,
                },
            )
            session.add(alert)
            await session.flush()
            await manager.broadcast(
                classroom_id,
                {
                    "type": "absence_alert",
                    "id": str(alert.id),
                    "uid": student.uid,
                    "student_name": student.name,
                    "classroom_id": classroom_id,
                    "duration_minutes": duration_minutes,
                    "last_seen_at": last_seen.isoformat() if last_seen else None,
                    "status": "active",
                },
            )
