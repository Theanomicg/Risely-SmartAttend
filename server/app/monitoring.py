from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import cv2
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.face import extract_embeddings_from_image
from app.models import ActiveAttendanceSession, Alert, CameraConfig, DetectionEvent, Student
from app.services.attendance import (
    calculate_absence_duration_minutes,
    ensure_default_monitoring_config,
    get_enabled_cameras,
    now_utc,
)
from app.services.presence import assign_face_matches
from app.ws import manager


settings = get_settings()
logger = logging.getLogger("smartattend.monitoring")


@dataclass
class CameraRuntimeStatus:
    class_id: str
    display_name: str
    enabled: bool
    status: str = "pending"
    last_checked_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    healthy_since: datetime | None = None


@dataclass(frozen=True)
class ActiveMonitoringStudent:
    class_id: str
    checked_in_at: datetime
    student: Student


@dataclass(frozen=True)
class CameraWorkerConfig:
    class_id: str
    display_name: str
    rtsp_url: str


class MonitoringService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory
        self.scheduler = AsyncIOScheduler()
        self._last_alert_run: datetime | None = None
        self._camera_status: dict[str, CameraRuntimeStatus] = {}
        self._status_lock = asyncio.Lock()
        self._camera_workers: dict[str, asyncio.Task] = {}
        self._camera_worker_configs: dict[str, CameraWorkerConfig] = {}
        self._worker_lock = asyncio.Lock()

    async def start(self) -> None:
        if self.scheduler.running:
            return
        self.scheduler.add_job(self.run_cycle, "interval", minutes=1, id="monitoring-loop")
        self.scheduler.start()
        await self.run_cycle(force_alert_evaluation=True)

    async def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        await self._stop_camera_workers()

    async def run_cycle(self, force_alert_evaluation: bool = False) -> None:
        async with self.session_factory() as session:
            config = await ensure_default_monitoring_config(session)
            monitored_class_ids = await self._sync_camera_workers(session)

            now = now_utc()
            if (
                not force_alert_evaluation
                and self._last_alert_run
                and now - self._last_alert_run < timedelta(minutes=config.monitoring_interval_minutes)
            ):
                return

            self._last_alert_run = now
            active_students = await self._get_active_students(session)
            health_windows = await self._get_camera_health_windows(monitored_class_ids)
            await self._resolve_inactive_alerts(
                session,
                active_keys={(active_student.student.uid, active_student.class_id) for active_student in active_students},
            )
            await self._raise_absence_alerts(
                session,
                config.absence_alert_threshold_minutes,
                health_windows,
                active_students=active_students,
            )
            await session.commit()

    def _open_capture(self, rtsp_url: str):
        capture = cv2.VideoCapture(rtsp_url)
        if capture.isOpened():
            return capture
        capture.release()
        return None

    def _read_frame(self, capture):
        ok, frame = capture.read()
        return frame if ok else None

    def _release_capture(self, capture) -> None:
        capture.release()

    async def _stop_camera_workers(self) -> None:
        async with self._worker_lock:
            tasks = list(self._camera_workers.values())
            self._camera_workers.clear()
            self._camera_worker_configs.clear()

        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _sync_camera_workers(self, session: AsyncSession) -> set[str]:
        cameras = await get_enabled_cameras(session)
        desired_configs = {
            camera.classroom_id: CameraWorkerConfig(
                class_id=camera.classroom_id,
                display_name=camera.display_name,
                rtsp_url=camera.rtsp_url,
            )
            for camera in cameras
        }

        tasks_to_cancel: list[asyncio.Task] = []
        tasks_to_start: list[CameraWorkerConfig] = []
        async with self._worker_lock:
            current_class_ids = set(self._camera_workers)
            desired_class_ids = set(desired_configs)

            for class_id in current_class_ids - desired_class_ids:
                task = self._camera_workers.pop(class_id)
                self._camera_worker_configs.pop(class_id, None)
                tasks_to_cancel.append(task)

            for class_id, desired_config in desired_configs.items():
                current_task = self._camera_workers.get(class_id)
                current_config = self._camera_worker_configs.get(class_id)
                should_restart = (
                    current_task is None
                    or current_task.done()
                    or current_config != desired_config
                )
                if not should_restart:
                    continue

                if current_task is not None:
                    self._camera_workers.pop(class_id, None)
                    tasks_to_cancel.append(current_task)
                self._camera_worker_configs[class_id] = desired_config
                tasks_to_start.append(desired_config)

        for task in tasks_to_cancel:
            task.cancel()
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

        async with self._worker_lock:
            for desired_config in tasks_to_start:
                self._camera_workers[desired_config.class_id] = asyncio.create_task(
                    self._camera_worker(desired_config),
                    name=f"camera-worker-{desired_config.class_id}",
                )

        return set(desired_configs)

    async def _camera_worker(self, camera: CameraWorkerConfig) -> None:
        capture = None
        reconnect_delay_seconds = 1

        try:
            while True:
                if capture is None:
                    capture = await asyncio.to_thread(self._open_capture, camera.rtsp_url)
                    if capture is None:
                        await self._set_camera_status(
                            camera.class_id,
                            display_name=camera.display_name,
                            enabled=True,
                            status="error",
                            last_error="Camera connection failed.",
                        )
                        await asyncio.sleep(reconnect_delay_seconds)
                        reconnect_delay_seconds = min(
                            reconnect_delay_seconds * 2,
                            settings.camera_reconnect_max_delay_seconds,
                        )
                        continue

                frame = await asyncio.to_thread(self._read_frame, capture)
                if frame is None:
                    await self._set_camera_status(
                        camera.class_id,
                        display_name=camera.display_name,
                        enabled=True,
                        status="error",
                        last_error="Camera frame capture failed.",
                    )
                    await asyncio.to_thread(self._release_capture, capture)
                    capture = None
                    await asyncio.sleep(reconnect_delay_seconds)
                    reconnect_delay_seconds = min(
                        reconnect_delay_seconds * 2,
                        settings.camera_reconnect_max_delay_seconds,
                    )
                    continue

                reconnect_delay_seconds = 1
                try:
                    async with self.session_factory() as session:
                        students = await self._get_active_students(session, class_id=camera.class_id)
                        if not students:
                            await self._set_camera_status(
                                camera.class_id,
                                display_name=camera.display_name,
                                enabled=True,
                                status="idle",
                                last_error=None,
                                mark_success=True,
                            )
                        else:
                            try:
                                observed_embeddings = await asyncio.to_thread(extract_embeddings_from_image, frame)
                            except ValueError:
                                observed_embeddings = []

                            await self._set_camera_status(
                                camera.class_id,
                                display_name=camera.display_name,
                                enabled=True,
                                status="online",
                                last_error=None,
                                mark_success=True,
                            )
                            logger.info(
                                "monitoring frame processed: class_id=%s camera=%s embeddings=%s",
                                camera.class_id,
                                camera.display_name,
                                len(observed_embeddings),
                            )
                            await self._record_matches(session, camera.class_id, students, observed_embeddings)
                            await session.commit()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    await self._set_camera_status(
                        camera.class_id,
                        display_name=camera.display_name,
                        enabled=True,
                        status="error",
                        last_error=f"Worker error: {exc}",
                    )
                    logger.warning(
                        "camera worker failed: class_id=%s camera=%s error=%s",
                        camera.class_id,
                        camera.display_name,
                        exc,
                    )

                await asyncio.sleep(settings.camera_sample_interval_seconds)
        except asyncio.CancelledError:
            raise
        finally:
            if capture is not None:
                await asyncio.to_thread(self._release_capture, capture)

    async def _set_camera_status(
        self,
        class_id: str,
        *,
        display_name: str,
        enabled: bool,
        status: str,
        last_error: str | None,
        mark_success: bool = False,
    ) -> None:
        now = now_utc()
        async with self._status_lock:
            current = self._camera_status.get(class_id) or CameraRuntimeStatus(
                class_id=class_id,
                display_name=display_name,
                enabled=enabled,
            )
            current.display_name = display_name
            current.enabled = enabled
            current.status = status
            current.last_checked_at = now
            current.last_error = last_error
            if mark_success:
                if current.healthy_since is None:
                    current.healthy_since = now
                current.last_success_at = now
            elif status in {"error", "disabled", "pending"}:
                current.healthy_since = None
            self._camera_status[class_id] = current

    async def _get_camera_health_windows(self, class_ids: set[str]) -> dict[str, datetime | None]:
        async with self._status_lock:
            return {
                class_id: (
                    self._camera_status.get(class_id).healthy_since
                    if self._camera_status.get(class_id)
                    else None
                )
                for class_id in class_ids
            }

    async def list_camera_statuses(self, session: AsyncSession) -> list[CameraRuntimeStatus]:
        result = await session.execute(select(CameraConfig).order_by(CameraConfig.classroom_id))
        cameras = list(result.scalars().all())
        async with self._status_lock:
            statuses = {key: value for key, value in self._camera_status.items()}

        results: list[CameraRuntimeStatus] = []
        for camera in cameras:
            existing = statuses.get(camera.classroom_id)
            if existing:
                existing.display_name = camera.display_name
                existing.enabled = camera.enabled
                if not camera.enabled:
                    existing.status = "disabled"
                results.append(existing)
                continue

            results.append(
                CameraRuntimeStatus(
                    class_id=camera.classroom_id,
                    display_name=camera.display_name,
                    enabled=camera.enabled,
                    status="disabled" if not camera.enabled else "pending",
                )
            )
        return sorted(results, key=lambda item: item.class_id)

    async def _get_active_students(
        self,
        session: AsyncSession,
        class_id: str | None = None,
    ) -> list[ActiveMonitoringStudent]:
        query = (
            select(ActiveAttendanceSession.classroom_id, ActiveAttendanceSession.checked_in_at, Student)
            .join(Student, Student.uid == ActiveAttendanceSession.uid)
        )
        if class_id:
            query = query.where(ActiveAttendanceSession.classroom_id == class_id)

        rows = (await session.execute(query)).all()
        return [
            ActiveMonitoringStudent(
                class_id=row[0],
                checked_in_at=row[1],
                student=row[2],
            )
            for row in rows
        ]

    async def _record_matches(
        self,
        session: AsyncSession,
        class_id: str,
        students: list[ActiveMonitoringStudent],
        observed_embeddings: list[list[float]],
    ) -> None:
        assignments = assign_face_matches(
            [active_student.student.face_embeddings for active_student in students],
            observed_embeddings,
            threshold=0.70,
        )
        matched_student_ids: set[str] = set()
        for assignment in assignments:
            student = students[assignment.student_index].student
            matched_student_ids.add(student.uid)
            session.add(
                DetectionEvent(
                    uid=student.uid,
                    classroom_id=class_id,
                    confidence=assignment.confidence,
                )
            )
        if not matched_student_ids:
            return

        resolved_at = now_utc()
        active_alerts = list(
            (
                await session.scalars(
                    select(Alert).where(
                        and_(
                            Alert.classroom_id == class_id,
                            Alert.status == "active",
                            Alert.uid.in_(sorted(matched_student_ids)),
                        )
                    )
                )
            ).all()
        )
        for active_alert in active_alerts:
            active_alert.status = "resolved"
            active_alert.acknowledged_at = resolved_at
            logger.info("alert resolved: uid=%s class_id=%s", active_alert.uid, class_id)
            await manager.broadcast(
                class_id,
                {
                    "type": "alert_resolved",
                    "id": str(active_alert.id),
                    "uid": active_alert.uid,
                    "class_id": class_id,
                    "status": "resolved",
                },
            )

    async def _raise_absence_alerts(
        self,
        session: AsyncSession,
        threshold_minutes: int,
        camera_health_windows: dict[str, datetime | None],
        *,
        active_students: list[ActiveMonitoringStudent],
    ) -> None:
        relevant_active_students = [
            active_student
            for active_student in active_students
            if camera_health_windows.get(active_student.class_id) is not None
        ]
        now = now_utc()
        if not relevant_active_students:
            return

        active_uids = sorted({active_student.student.uid for active_student in relevant_active_students})
        last_seen_rows = (
            await session.execute(
                select(
                    DetectionEvent.uid,
                    DetectionEvent.classroom_id,
                    func.max(DetectionEvent.timestamp).label("last_seen_at"),
                )
                .where(DetectionEvent.uid.in_(active_uids))
                .group_by(DetectionEvent.uid, DetectionEvent.classroom_id)
            )
        ).all()
        last_seen_by_key = {(uid, classroom_id): last_seen_at for uid, classroom_id, last_seen_at in last_seen_rows}
        active_alert_rows = (
            await session.execute(
                select(Alert.uid, Alert.classroom_id).where(
                    and_(
                        Alert.status == "active",
                        Alert.uid.in_(active_uids),
                    )
                )
            )
        ).all()
        active_alert_keys = {(uid, classroom_id) for uid, classroom_id in active_alert_rows}

        for active_student in relevant_active_students:
            student = active_student.student
            class_id = active_student.class_id
            key = (student.uid, class_id)
            last_seen = last_seen_by_key.get(key)
            duration_minutes = calculate_absence_duration_minutes(
                checked_in_at=active_student.checked_in_at,
                last_seen_at=last_seen,
                now=now,
                threshold_minutes=threshold_minutes,
                monitoring_active_since=camera_health_windows.get(class_id),
            )
            if duration_minutes is None:
                continue

            if key in active_alert_keys:
                continue

            absent_since_at = last_seen or active_student.checked_in_at
            monitoring_active_since = camera_health_windows.get(class_id)
            if monitoring_active_since and monitoring_active_since > absent_since_at:
                absent_since_at = monitoring_active_since

            alert = Alert(
                uid=student.uid,
                classroom_id=class_id,
                status="active",
                payload={
                    "student_name": student.name,
                    "duration_minutes": duration_minutes,
                    "absent_since_at": absent_since_at.isoformat(),
                    "last_seen_at": last_seen.isoformat() if last_seen else None,
                },
            )
            session.add(alert)
            await session.flush()
            active_alert_keys.add(key)
            logger.warning(
                "absence alert raised: uid=%s class_id=%s duration_minutes=%s",
                student.uid,
                class_id,
                duration_minutes,
            )
            await manager.broadcast(
                class_id,
                {
                    "type": "absence_alert",
                    "id": str(alert.id),
                    "uid": student.uid,
                    "student_name": student.name,
                    "class_id": class_id,
                    "duration_minutes": duration_minutes,
                    "last_seen_at": last_seen.isoformat() if last_seen else None,
                    "status": "active",
                },
            )

    async def _resolve_inactive_alerts(
        self,
        session: AsyncSession,
        *,
        active_keys: set[tuple[str, str]],
    ) -> None:
        alerts = list((await session.scalars(select(Alert).where(Alert.status == "active"))).all())
        if not alerts:
            return

        resolved_at = now_utc()
        for alert in alerts:
            if (alert.uid, alert.classroom_id) in active_keys:
                continue
            alert.status = "resolved"
            alert.acknowledged_at = resolved_at
            logger.info("inactive alert resolved: uid=%s class_id=%s", alert.uid, alert.classroom_id)
            await manager.broadcast(
                alert.classroom_id,
                {
                    "type": "alert_resolved",
                    "id": str(alert.id),
                    "uid": alert.uid,
                    "class_id": alert.classroom_id,
                    "status": "resolved",
                },
            )
