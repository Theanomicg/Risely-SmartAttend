from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CheckEventRequest(BaseModel):
    classroom_id: str
    embedding: list[float] = Field(..., min_length=128, max_length=128)
    device_id: str | None = None
    confidence: float | None = None
    matched_uid: str | None = None


class CheckEventResponse(BaseModel):
    success: bool
    message: str
    uid: str | None = None
    student_name: str | None = None
    confidence: float | None = None


class ActiveStudentResponse(BaseModel):
    uid: str
    name: str
    class_id: str
    classroom_id: str
    checked_in_at: datetime
    last_seen_at: datetime | None = None


class StudentRegistrationResponse(BaseModel):
    uid: str
    name: str
    class_id: str
    embedding_count: int


class CameraConfigIn(BaseModel):
    classroom_id: str
    display_name: str
    rtsp_url: str
    enabled: bool = True


class CameraConfigOut(CameraConfigIn):
    pass


class MonitoringSettingsIn(BaseModel):
    monitoring_interval_minutes: int = Field(..., ge=1, le=60)
    absence_alert_threshold_minutes: int = Field(..., ge=1, le=240)


class MonitoringSettingsOut(MonitoringSettingsIn):
    pass


class AlertResponse(BaseModel):
    id: UUID
    uid: str
    student_name: str
    classroom_id: str
    status: str
    duration_minutes: int
    last_seen_at: datetime | None
    created_at: datetime


class AlertAcknowledgeResponse(BaseModel):
    id: UUID
    status: str


class AlertDismissResponse(BaseModel):
    id: UUID
    status: str
