from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "SmartAttend API"
    database_url: str = Field(
        default="postgresql+asyncpg://smartattend:smartattend@localhost:5432/smartattend",
        alias="DATABASE_URL",
    )
    server_host: str = Field(default="0.0.0.0", alias="SERVER_HOST")
    server_port: int = Field(default=8000, alias="SERVER_PORT")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )
    embedding_dim: int = Field(default=128, alias="EMBEDDING_DIM")
    face_model_name: str = Field(default="ArcFace", alias="FACE_MODEL_NAME")
    detector_backends: str = Field(default="retinaface,mtcnn,opencv", alias="DETECTOR_BACKENDS")
    face_distance_threshold: float = Field(default=0.35, alias="FACE_DISTANCE_THRESHOLD")
    monitoring_interval_minutes: int = Field(default=5, alias="MONITORING_INTERVAL_MINUTES")
    absence_alert_threshold_minutes: int = Field(default=15, alias="ABSENCE_ALERT_THRESHOLD_MINUTES")
    camera_sample_interval_seconds: int = Field(default=5, alias="CAMERA_SAMPLE_INTERVAL_SECONDS", ge=1, le=60)
    camera_reconnect_max_delay_seconds: int = Field(default=30, alias="CAMERA_RECONNECT_MAX_DELAY_SECONDS", ge=1, le=300)
    min_registration_embeddings: int = Field(default=3, alias="MIN_REGISTRATION_EMBEDDINGS")
    enrollment_photo_dir: str = Field(default="storage/enrollment_photos", alias="ENROLLMENT_PHOTO_DIR")
    teacher_token: str = Field(default="", alias="TEACHER_TOKEN")
    admin_token: str = Field(default="", alias="ADMIN_TOKEN")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def detector_backend_list(self) -> list[str]:
        return [backend.strip() for backend in self.detector_backends.split(",") if backend.strip()]

    @property
    def enrollment_photo_path(self) -> Path:
        return Path(self.enrollment_photo_dir)

    @property
    def auth_enabled(self) -> bool:
        return bool(self.teacher_token or self.admin_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()
