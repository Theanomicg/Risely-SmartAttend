from functools import lru_cache

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
    min_registration_embeddings: int = Field(default=3, alias="MIN_REGISTRATION_EMBEDDINGS")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def detector_backend_list(self) -> list[str]:
        return [backend.strip() for backend in self.detector_backends.split(",") if backend.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
