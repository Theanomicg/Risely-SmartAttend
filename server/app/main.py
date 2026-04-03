from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pgvector.utils import Vector as PgVector
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import authorize_websocket, require_admin_access, require_teacher_access
from app.config import get_settings
from app.db import Base, SessionLocal, engine, get_db
from app.face import extract_embeddings_from_bytes
from app.models import ActiveAttendanceSession, Alert, AttendanceEvent, CameraConfig, Student, StudentPhoto
from app.monitoring import MonitoringService
from app.schemas import (
    ActiveStudentResponse,
    AttendanceSessionResponse,
    AlertAcknowledgeResponse,
    AlertDismissResponse,
    AlertResponse,
    CameraConfigIn,
    CameraHealthResponse,
    CameraConfigOut,
    CheckEventRequest,
    CheckEventResponse,
    MonitoringSettingsIn,
    MonitoringSettingsOut,
    StudentListResponse,
    StudentDeleteResponse,
    StudentPhotoResponse,
    StudentRegistrationResponse,
    SystemStatusResponse,
)
from app.services.attendance import (
    calculate_current_alert_duration_minutes,
    ensure_default_monitoring_config,
    get_active_attendance_session,
    list_active_students,
    list_attendance_sessions,
    now_utc,
    rebuild_active_attendance_state,
    resolve_active_alerts,
    validate_active_attendance_transition,
)
from app.services.matching import find_best_student_match
from app.storage import delete_student_photo_dir, ensure_storage_dirs, resolve_student_photo, save_student_photo
from app.ws import manager


settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("smartattend.api")
app = FastAPI(title=settings.app_name)
monitoring_service = MonitoringService(SessionLocal)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def mask_rtsp_url(value: str) -> str:
    if "@" not in value:
        return value
    credentials, host = value.split("@", 1)
    if "://" not in credentials:
        return value
    scheme, _ = credentials.split("://", 1)
    return f"{scheme}://***:***@{host}"


@app.on_event("startup")
async def startup() -> None:
    ensure_storage_dirs()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        rebuilt_count = await rebuild_active_attendance_state(session)
        await session.commit()
    logger.info("active attendance state rebuilt: sessions=%s", rebuilt_count)
    await monitoring_service.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await monitoring_service.stop()
    await engine.dispose()


@app.get("/health", response_model=SystemStatusResponse)
async def health() -> SystemStatusResponse:
    return SystemStatusResponse(api_status="ok", auth_enabled=settings.auth_enabled)


@app.get("/system/status", response_model=SystemStatusResponse, dependencies=[Depends(require_teacher_access)])
async def system_status() -> SystemStatusResponse:
    return SystemStatusResponse(api_status="ok", auth_enabled=settings.auth_enabled)


@app.post("/checkin", response_model=CheckEventResponse)
async def checkin(payload: CheckEventRequest, session: AsyncSession = Depends(get_db)) -> CheckEventResponse:
    match = await find_best_student_match(session, payload.embedding, class_id=payload.class_id)
    if not match.uid:
        logger.info("checkin rejected: face not recognized for class_id=%s device_id=%s", payload.class_id, payload.device_id)
        return CheckEventResponse(success=False, message="Face not recognized.", confidence=match.confidence)

    active_session = await get_active_attendance_session(session, match.uid)
    decision = validate_active_attendance_transition("checkin", payload.class_id, active_session)
    if not decision.should_create_event:
        logger.info(
            "checkin skipped: uid=%s class_id=%s message=%s",
            match.uid,
            payload.class_id,
            decision.message,
        )
        return CheckEventResponse(
            success=decision.success,
            message=decision.message,
            uid=match.uid,
            student_name=match.student_name,
            confidence=match.confidence,
        )

    event_time = now_utc()
    session.add(
        AttendanceEvent(
            uid=match.uid,
            event_type="checkin",
            timestamp=event_time,
            classroom_id=payload.class_id,
            source="kiosk",
        )
    )
    session.add(
        ActiveAttendanceSession(
            uid=match.uid,
            classroom_id=payload.class_id,
            checked_in_at=event_time,
        )
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        active_session = await get_active_attendance_session(session, match.uid)
        decision = validate_active_attendance_transition("checkin", payload.class_id, active_session)
        if not decision.should_create_event:
            return CheckEventResponse(
                success=decision.success,
                message=decision.message,
                uid=match.uid,
                student_name=match.student_name,
                confidence=match.confidence,
            )
        raise HTTPException(status_code=409, detail="Active attendance state conflict.") from exc
    logger.info("checkin recorded: uid=%s class_id=%s", match.uid, payload.class_id)
    return CheckEventResponse(
        success=True,
        message=decision.message,
        uid=match.uid,
        student_name=match.student_name,
        confidence=match.confidence,
    )


@app.post("/checkout", response_model=CheckEventResponse)
async def checkout(payload: CheckEventRequest, session: AsyncSession = Depends(get_db)) -> CheckEventResponse:
    match = await find_best_student_match(session, payload.embedding, class_id=payload.class_id)
    if not match.uid:
        logger.info("checkout rejected: face not recognized for class_id=%s device_id=%s", payload.class_id, payload.device_id)
        return CheckEventResponse(success=False, message="Face not recognized.", confidence=match.confidence)

    active_session = await get_active_attendance_session(session, match.uid)
    decision = validate_active_attendance_transition("checkout", payload.class_id, active_session)
    if not decision.should_create_event:
        logger.info(
            "checkout skipped: uid=%s class_id=%s message=%s",
            match.uid,
            payload.class_id,
            decision.message,
        )
        return CheckEventResponse(
            success=decision.success,
            message=decision.message,
            uid=match.uid,
            student_name=match.student_name,
            confidence=match.confidence,
        )

    event_time = now_utc()
    session.add(
        AttendanceEvent(
            uid=match.uid,
            event_type="checkout",
            timestamp=event_time,
            classroom_id=payload.class_id,
            source="kiosk",
        )
    )
    if active_session:
        await session.delete(active_session)
    resolved_alerts = await resolve_active_alerts(
        session,
        uid=match.uid,
        class_id=payload.class_id,
        resolved_at=event_time,
    )
    await session.commit()
    for alert in resolved_alerts:
        await manager.broadcast(
            payload.class_id,
            {
                "type": "alert_resolved",
                "id": str(alert.id),
                "uid": match.uid,
                "class_id": payload.class_id,
                "status": "resolved",
            },
        )
    logger.info("checkout recorded: uid=%s class_id=%s", match.uid, payload.class_id)
    return CheckEventResponse(
        success=True,
        message=decision.message,
        uid=match.uid,
        student_name=match.student_name,
        confidence=match.confidence,
    )


@app.get("/active-students", response_model=list[ActiveStudentResponse], dependencies=[Depends(require_teacher_access)])
async def active_students(
    class_id: str | None = Query(default=None, alias="class_id"),
    classroom_id: str | None = Query(default=None, alias="classroom_id"),
    session: AsyncSession = Depends(get_db),
) -> list[ActiveStudentResponse]:
    rows = await list_active_students(session, class_id or classroom_id)
    return [ActiveStudentResponse(**row) for row in rows]


@app.get("/attendance-sessions", response_model=list[AttendanceSessionResponse], dependencies=[Depends(require_teacher_access)])
async def attendance_sessions(
    class_id: str | None = Query(default=None, alias="class_id"),
    classroom_id: str | None = Query(default=None, alias="classroom_id"),
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
) -> list[AttendanceSessionResponse]:
    rows = await list_attendance_sessions(session, class_id=class_id or classroom_id, limit=limit)
    return [AttendanceSessionResponse(**row) for row in rows]


@app.get("/alerts", response_model=list[AlertResponse], dependencies=[Depends(require_teacher_access)])
async def get_alerts(
    class_id: str | None = Query(default=None, alias="class_id"),
    classroom_id: str | None = Query(default=None, alias="classroom_id"),
    session: AsyncSession = Depends(get_db),
) -> list[AlertResponse]:
    now = now_utc()
    query = (
        select(Alert, Student.name)
        .join(Student, Student.uid == Alert.uid)
        .where(Alert.status == "active")
        .order_by(desc(Alert.created_at))
    )
    effective_class_id = class_id or classroom_id
    if effective_class_id:
        query = query.where(Alert.classroom_id == effective_class_id)

    rows = (await session.execute(query)).all()
    alerts: list[AlertResponse] = []
    for alert, student_name in rows:
        last_seen_raw = alert.payload.get("last_seen_at")
        alerts.append(
            AlertResponse(
                id=alert.id,
                uid=alert.uid,
                student_name=student_name,
                class_id=alert.classroom_id,
                status=alert.status,
                duration_minutes=calculate_current_alert_duration_minutes(
                    created_at=alert.created_at,
                    payload=alert.payload,
                    now=now,
                ),
                last_seen_at=datetime.fromisoformat(last_seen_raw) if last_seen_raw else None,
                created_at=alert.created_at,
            )
        )
    return alerts


@app.post("/alerts/{alert_id}/acknowledge", response_model=AlertAcknowledgeResponse, dependencies=[Depends(require_teacher_access)])
async def acknowledge_alert(alert_id: UUID, session: AsyncSession = Depends(get_db)) -> AlertAcknowledgeResponse:
    alert = await session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")
    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.now(timezone.utc)
    await session.commit()
    await manager.broadcast(
        alert.classroom_id,
        {
            "type": "alert_resolved",
            "id": str(alert.id),
            "uid": alert.uid,
            "class_id": alert.classroom_id,
            "status": alert.status,
        },
    )
    return AlertAcknowledgeResponse(id=alert.id, status=alert.status)


@app.post("/alerts/{alert_id}/dismiss", response_model=AlertDismissResponse, dependencies=[Depends(require_teacher_access)])
async def dismiss_alert(alert_id: UUID, session: AsyncSession = Depends(get_db)) -> AlertDismissResponse:
    alert = await session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")
    alert.status = "dismissed"
    alert.acknowledged_at = datetime.now(timezone.utc)
    await session.commit()
    await manager.broadcast(
        alert.classroom_id,
        {
            "type": "alert_resolved",
            "id": str(alert.id),
            "uid": alert.uid,
            "class_id": alert.classroom_id,
            "status": alert.status,
        },
    )
    return AlertDismissResponse(id=alert.id, status=alert.status)


@app.post("/admin/students", response_model=StudentRegistrationResponse, dependencies=[Depends(require_admin_access)])
async def register_student(
    uid: str = Form(...),
    name: str = Form(...),
    class_id: str = Form(...),
    photos: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_db),
) -> StudentRegistrationResponse:
    if len(photos) < 5:
        raise HTTPException(status_code=400, detail="Upload at least 5 photos.")

    image_bytes = [await file.read() for file in photos]
    try:
        embeddings, failures = extract_embeddings_from_bytes(image_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {exc}") from exc
    if len(embeddings) < settings.min_registration_embeddings:
        failure_summary = " ".join(failures[:3])
        raise HTTPException(
            status_code=400,
            detail=(
                f"Only {len(embeddings)} valid face embedding(s) were extracted. "
                f"At least {settings.min_registration_embeddings} are required. {failure_summary}"
            ).strip(),
        )

    student = Student(
        uid=uid,
        name=name,
        class_id=class_id,
        face_embeddings=[PgVector(embedding) for embedding in embeddings],
    )
    session.add(student)
    photo_count = 0
    for upload, raw in zip(photos, image_bytes):
        relative_path = save_student_photo(uid, upload.filename or "photo.jpg", raw)
        session.add(
            StudentPhoto(
                uid=uid,
                file_path=relative_path,
                original_filename=upload.filename or Path(relative_path).name,
            )
        )
        photo_count += 1
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Student UID already exists.") from exc
    return StudentRegistrationResponse(
        uid=uid,
        name=name,
        class_id=class_id,
        embedding_count=len(embeddings),
        photo_count=photo_count,
    )


@app.get("/admin/students", response_model=list[StudentListResponse], dependencies=[Depends(require_admin_access)])
async def list_students(session: AsyncSession = Depends(get_db)) -> list[StudentListResponse]:
    result = await session.execute(select(Student).options(selectinload(Student.photos)).order_by(Student.name))
    return [
        StudentListResponse(
            uid=student.uid,
            name=student.name,
            class_id=student.class_id,
            embedding_count=len(student.face_embeddings),
            photo_count=len(student.photos),
            photos=[
                StudentPhotoResponse(
                    id=photo.id,
                    original_filename=photo.original_filename,
                    url=f"/api/admin/students/{student.uid}/photos/{photo.id}",
                )
                for photo in student.photos
            ],
        )
        for student in result.scalars().all()
    ]


@app.delete("/admin/students/{uid}", response_model=StudentDeleteResponse, dependencies=[Depends(require_admin_access)])
async def delete_student(uid: str, session: AsyncSession = Depends(get_db)) -> StudentDeleteResponse:
    student = await session.scalar(select(Student).where(Student.uid == uid))
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    active_alerts = list(
        (
            await session.scalars(
                select(Alert).where(
                    Alert.uid == uid,
                    Alert.status == "active",
                )
            )
        ).all()
    )
    alert_broadcasts = [
        {
            "id": str(alert.id),
            "uid": alert.uid,
            "class_id": alert.classroom_id,
            "status": "resolved",
        }
        for alert in active_alerts
    ]

    await session.delete(student)
    await session.commit()

    photo_cleanup_warning = False
    try:
        delete_student_photo_dir(uid)
    except Exception as exc:
        photo_cleanup_warning = True
        logger.warning("student photo cleanup failed: uid=%s error=%s", uid, exc)

    for payload in alert_broadcasts:
        await manager.broadcast(
            payload["class_id"],
            {
                "type": "alert_resolved",
                **payload,
            },
        )

    return StudentDeleteResponse(
        uid=uid,
        deleted=True,
        message=(
            "Student deleted successfully."
            if not photo_cleanup_warning
            else "Student deleted, but some enrollment photo files could not be removed."
        ),
    )


@app.get("/admin/students/{uid}/photos/{photo_id}", dependencies=[Depends(require_admin_access)])
async def get_student_photo(uid: str, photo_id: int, session: AsyncSession = Depends(get_db)) -> FileResponse:
    photo = await session.scalar(select(StudentPhoto).where(StudentPhoto.uid == uid, StudentPhoto.id == photo_id))
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found.")

    try:
        file_path = resolve_student_photo(photo.file_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Photo file not found.")
    return FileResponse(path=file_path, filename=photo.original_filename)


@app.post("/admin/cameras", response_model=CameraConfigOut, dependencies=[Depends(require_admin_access)])
async def upsert_camera(config_in: CameraConfigIn, session: AsyncSession = Depends(get_db)) -> CameraConfigOut:
    camera = await session.get(CameraConfig, config_in.class_id)
    if camera:
        camera.display_name = config_in.display_name
        camera.rtsp_url = config_in.rtsp_url
        camera.enabled = config_in.enabled
    else:
        camera = CameraConfig(
            classroom_id=config_in.class_id,
            display_name=config_in.display_name,
            rtsp_url=config_in.rtsp_url,
            enabled=config_in.enabled,
        )
        session.add(camera)
    await session.commit()
    return CameraConfigOut(
        class_id=camera.classroom_id,
        display_name=camera.display_name,
        rtsp_url="",
        rtsp_url_masked=mask_rtsp_url(camera.rtsp_url),
        enabled=camera.enabled,
    )


@app.get("/admin/cameras", response_model=list[CameraConfigOut], dependencies=[Depends(require_admin_access)])
async def list_cameras(session: AsyncSession = Depends(get_db)) -> list[CameraConfigOut]:
    result = await session.execute(select(CameraConfig).order_by(CameraConfig.classroom_id))
    return [
        CameraConfigOut(
            class_id=camera.classroom_id,
            display_name=camera.display_name,
            rtsp_url="",
            rtsp_url_masked=mask_rtsp_url(camera.rtsp_url),
            enabled=camera.enabled,
        )
        for camera in result.scalars().all()
    ]


@app.get("/admin/camera-status", response_model=list[CameraHealthResponse], dependencies=[Depends(require_admin_access)])
async def list_camera_statuses(session: AsyncSession = Depends(get_db)) -> list[CameraHealthResponse]:
    statuses = await monitoring_service.list_camera_statuses(session)
    return [
        CameraHealthResponse(
            class_id=status.class_id,
            display_name=status.display_name,
            enabled=status.enabled,
            status=status.status,
            last_checked_at=status.last_checked_at,
            last_success_at=status.last_success_at,
            last_error=status.last_error,
        )
        for status in statuses
    ]


@app.get("/admin/settings", response_model=MonitoringSettingsOut, dependencies=[Depends(require_admin_access)])
async def get_settings_endpoint(session: AsyncSession = Depends(get_db)) -> MonitoringSettingsOut:
    config = await ensure_default_monitoring_config(session)
    return MonitoringSettingsOut(
        monitoring_interval_minutes=config.monitoring_interval_minutes,
        absence_alert_threshold_minutes=config.absence_alert_threshold_minutes,
    )


@app.put("/admin/settings", response_model=MonitoringSettingsOut, dependencies=[Depends(require_admin_access)])
async def update_settings(payload: MonitoringSettingsIn, session: AsyncSession = Depends(get_db)) -> MonitoringSettingsOut:
    config = await ensure_default_monitoring_config(session)
    config.monitoring_interval_minutes = payload.monitoring_interval_minutes
    config.absence_alert_threshold_minutes = payload.absence_alert_threshold_minutes
    await session.commit()
    return MonitoringSettingsOut(**payload.model_dump())


@app.websocket("/ws/alerts/{class_id}")
async def alerts_websocket(websocket: WebSocket, class_id: str) -> None:
    try:
        authorize_websocket(websocket.query_params.get("token"))
    except HTTPException:
        await websocket.close(code=1008)
        return
    await manager.connect(class_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(class_id, websocket)
