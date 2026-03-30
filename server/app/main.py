from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pgvector.utils import Vector as PgVector
from sqlalchemy.exc import IntegrityError
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import Base, SessionLocal, engine, get_db
from app.face import extract_embeddings_from_bytes
from app.models import Alert, AttendanceEvent, CameraConfig, Student
from app.monitoring import MonitoringService
from app.schemas import (
    ActiveStudentResponse,
    AlertAcknowledgeResponse,
    AlertDismissResponse,
    AlertResponse,
    CameraConfigIn,
    CameraConfigOut,
    CheckEventRequest,
    CheckEventResponse,
    MonitoringSettingsIn,
    MonitoringSettingsOut,
    StudentRegistrationResponse,
)
from app.services.attendance import ensure_default_monitoring_config, list_active_students
from app.services.matching import find_best_student_match
from app.ws import manager


settings = get_settings()
app = FastAPI(title=settings.app_name)
monitoring_service = MonitoringService(SessionLocal)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monitoring_service.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    monitoring_service.stop()
    await engine.dispose()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/checkin", response_model=CheckEventResponse)
async def checkin(payload: CheckEventRequest, session: AsyncSession = Depends(get_db)) -> CheckEventResponse:
    match = await find_best_student_match(session, payload.embedding)
    if not match.uid:
        return CheckEventResponse(success=False, message="Face not recognized.", confidence=match.confidence)

    session.add(
        AttendanceEvent(
            uid=match.uid,
            event_type="checkin",
            classroom_id=payload.classroom_id,
            source="kiosk",
        )
    )
    await session.commit()
    return CheckEventResponse(
        success=True,
        message="Check-in successful.",
        uid=match.uid,
        student_name=match.student_name,
        confidence=match.confidence,
    )


@app.post("/checkout", response_model=CheckEventResponse)
async def checkout(payload: CheckEventRequest, session: AsyncSession = Depends(get_db)) -> CheckEventResponse:
    match = await find_best_student_match(session, payload.embedding)
    if not match.uid:
        return CheckEventResponse(success=False, message="Face not recognized.", confidence=match.confidence)

    session.add(
        AttendanceEvent(
            uid=match.uid,
            event_type="checkout",
            classroom_id=payload.classroom_id,
            source="kiosk",
        )
    )
    await session.commit()
    return CheckEventResponse(
        success=True,
        message="Check-out successful.",
        uid=match.uid,
        student_name=match.student_name,
        confidence=match.confidence,
    )


@app.get("/active-students", response_model=list[ActiveStudentResponse])
async def active_students(
    classroom_id: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> list[ActiveStudentResponse]:
    rows = await list_active_students(session, classroom_id)
    return [ActiveStudentResponse(**row) for row in rows]


@app.get("/alerts", response_model=list[AlertResponse])
async def get_alerts(classroom_id: str | None = None, session: AsyncSession = Depends(get_db)) -> list[AlertResponse]:
    query = (
        select(Alert, Student.name)
        .join(Student, Student.uid == Alert.uid)
        .where(Alert.status == "active")
        .order_by(desc(Alert.created_at))
    )
    if classroom_id:
        query = query.where(Alert.classroom_id == classroom_id)

    rows = (await session.execute(query)).all()
    alerts: list[AlertResponse] = []
    for alert, student_name in rows:
        last_seen_raw = alert.payload.get("last_seen_at")
        alerts.append(
            AlertResponse(
                id=alert.id,
                uid=alert.uid,
                student_name=student_name,
                classroom_id=alert.classroom_id,
                status=alert.status,
                duration_minutes=int(alert.payload.get("duration_minutes", 0)),
                last_seen_at=datetime.fromisoformat(last_seen_raw) if last_seen_raw else None,
                created_at=alert.created_at,
            )
        )
    return alerts


@app.post("/alerts/{alert_id}/acknowledge", response_model=AlertAcknowledgeResponse)
async def acknowledge_alert(alert_id: str, session: AsyncSession = Depends(get_db)) -> AlertAcknowledgeResponse:
    alert = await session.get(Alert, UUID(alert_id))
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")
    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.now(timezone.utc)
    await session.commit()
    return AlertAcknowledgeResponse(id=alert.id, status=alert.status)


@app.post("/alerts/{alert_id}/dismiss", response_model=AlertDismissResponse)
async def dismiss_alert(alert_id: str, session: AsyncSession = Depends(get_db)) -> AlertDismissResponse:
    alert = await session.get(Alert, UUID(alert_id))
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")
    alert.status = "dismissed"
    alert.acknowledged_at = datetime.now(timezone.utc)
    await session.commit()
    return AlertDismissResponse(id=alert.id, status=alert.status)


@app.post("/admin/students", response_model=StudentRegistrationResponse)
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
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Student UID already exists.") from exc
    return StudentRegistrationResponse(uid=uid, name=name, class_id=class_id, embedding_count=len(embeddings))


@app.get("/admin/students")
async def list_students(session: AsyncSession = Depends(get_db)) -> list[dict]:
    result = await session.execute(select(Student).order_by(Student.name))
    return [
        {
            "uid": student.uid,
            "name": student.name,
            "class_id": student.class_id,
            "embedding_count": len(student.face_embeddings),
        }
        for student in result.scalars().all()
    ]


@app.post("/admin/cameras", response_model=CameraConfigOut)
async def upsert_camera(config_in: CameraConfigIn, session: AsyncSession = Depends(get_db)) -> CameraConfigOut:
    camera = await session.get(CameraConfig, config_in.classroom_id)
    if camera:
        camera.display_name = config_in.display_name
        camera.rtsp_url = config_in.rtsp_url
        camera.enabled = config_in.enabled
    else:
        camera = CameraConfig(**config_in.model_dump())
        session.add(camera)
    await session.commit()
    return CameraConfigOut(**config_in.model_dump())


@app.get("/admin/cameras", response_model=list[CameraConfigOut])
async def list_cameras(session: AsyncSession = Depends(get_db)) -> list[CameraConfigOut]:
    result = await session.execute(select(CameraConfig).order_by(CameraConfig.classroom_id))
    return [
        CameraConfigOut(
            classroom_id=camera.classroom_id,
            display_name=camera.display_name,
            rtsp_url=camera.rtsp_url,
            enabled=camera.enabled,
        )
        for camera in result.scalars().all()
    ]


@app.get("/admin/settings", response_model=MonitoringSettingsOut)
async def get_settings_endpoint(session: AsyncSession = Depends(get_db)) -> MonitoringSettingsOut:
    config = await ensure_default_monitoring_config(session)
    return MonitoringSettingsOut(
        monitoring_interval_minutes=config.monitoring_interval_minutes,
        absence_alert_threshold_minutes=config.absence_alert_threshold_minutes,
    )


@app.put("/admin/settings", response_model=MonitoringSettingsOut)
async def update_settings(payload: MonitoringSettingsIn, session: AsyncSession = Depends(get_db)) -> MonitoringSettingsOut:
    config = await ensure_default_monitoring_config(session)
    config.monitoring_interval_minutes = payload.monitoring_interval_minutes
    config.absence_alert_threshold_minutes = payload.absence_alert_threshold_minutes
    await session.commit()
    return MonitoringSettingsOut(**payload.model_dump())


@app.websocket("/ws/alerts/{classroom_id}")
async def alerts_websocket(websocket: WebSocket, classroom_id: str) -> None:
    await manager.connect(classroom_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(classroom_id, websocket)
