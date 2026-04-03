from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import requests
from requests import RequestException


def parse_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def env_string(primary_key: str, fallback_key: str | None = None, default: str = "") -> str:
    if fallback_key:
        return os.getenv(primary_key, os.getenv(fallback_key, default))
    return os.getenv(primary_key, default)


def env_int(key: str, default: int) -> int:
    raw_value = os.getenv(key)
    if raw_value is None:
        return default
    return int(raw_value)


def load_deepface():
    from deepface import DeepFace

    return DeepFace


def load_env_file(env_path: Path | None = None) -> dict[str, str]:
    env_file = env_path or Path(__file__).with_name(".env")
    values = parse_env_file(env_file)
    for key, value in values.items():
        os.environ[key] = value
    return values


def normalize_api_host(host: str) -> str:
    normalized = host.strip()
    if not normalized or normalized in {"0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    return normalized


def infer_backend_api_url(default: str = "http://localhost:8000") -> str:
    configured_api_url = env_string("SMARTATTEND_API_URL").strip()
    if configured_api_url and configured_api_url.lower() != "auto":
        return configured_api_url

    server_env_path = Path(__file__).resolve().parents[1] / "server" / ".env"
    server_values = parse_env_file(server_env_path)
    if not server_values:
        return default

    host = normalize_api_host(server_values.get("SERVER_HOST", "127.0.0.1"))
    port = server_values.get("SERVER_PORT", "8000").strip() or "8000"
    if not port.isdigit():
        port = "8000"
    return f"http://{host}:{port}"


@dataclass
class KioskConfig:
    api_url: str = field(default_factory=infer_backend_api_url)
    class_id: str = field(
        default_factory=lambda: env_string("SMARTATTEND_CLASS_ID", "SMARTATTEND_CLASSROOM_ID", "class-10-a")
    )
    device_id: str = field(default_factory=lambda: env_string("SMARTATTEND_DEVICE_ID", default="pi-kiosk-01"))
    camera_source: str = field(default_factory=lambda: env_string("SMARTATTEND_CAMERA_SOURCE"))
    camera_index: int = field(default_factory=lambda: env_int("SMARTATTEND_CAMERA_INDEX", 1))
    camera_backend: str = field(default_factory=lambda: env_string("SMARTATTEND_CAMERA_BACKEND", default="auto"))
    action: str = field(default_factory=lambda: env_string("SMARTATTEND_ACTION", default="checkin"))
    face_model: str = field(default_factory=lambda: env_string("SMARTATTEND_FACE_MODEL", default="ArcFace"))
    embedding_dim: int = field(default_factory=lambda: env_int("SMARTATTEND_EMBEDDING_DIM", 128))

    def __post_init__(self) -> None:
        self.api_url = self.api_url.rstrip("/")
        self.class_id = self.class_id.strip() or "class-10-a"
        self.device_id = self.device_id.strip() or "pi-kiosk-01"
        self.camera_backend = self.camera_backend.strip().lower() or "auto"
        self.face_model = self.face_model.strip() or "ArcFace"
        self.action = self.action.strip().lower().lstrip("/")
        if self.action not in {"checkin", "checkout"}:
            raise ValueError("SMARTATTEND_ACTION must be either 'checkin' or 'checkout'.")


class SmartAttendKiosk:
    def __init__(self, config: KioskConfig) -> None:
        self.config = config
        source, backend = self._resolve_camera_target()
        self.source = source
        self.backend = backend
        self.capture = cv2.VideoCapture(source, backend)
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        print(f"SmartAttend kiosk API base={self.config.api_url}")
        print(f"SmartAttend kiosk camera source={self.source!r} backend={self.backend}")

    def _resolve_camera_target(self) -> tuple[int | str, int]:
        if self.config.camera_source:
            source: int | str = (
                int(self.config.camera_source)
                if self.config.camera_source.isdigit()
                else self.config.camera_source
            )
        else:
            source = self.config.camera_index

        backend_name = self.config.camera_backend.lower()
        if backend_name == "dshow":
            return source, cv2.CAP_DSHOW
        if backend_name == "msmf":
            return source, cv2.CAP_MSMF
        if platform.system() == "Windows":
            return source, cv2.CAP_DSHOW
        return source, cv2.CAP_ANY

    def run(self) -> None:
        while True:
            ok, frame = self.capture.read()
            if not ok:
                self._render_status(None, "Camera read failed.", (0, 0, 255))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            cv2.putText(
                frame,
                f"Camera source: {self.source}",
                (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow("SmartAttend Kiosk", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("c"):
                self.process_frame(frame)
            elif key == ord("q"):
                break

        self.capture.release()
        cv2.destroyAllWindows()

    def process_frame(self, frame: np.ndarray) -> None:
        try:
            embedding = self.extract_embedding(frame)
        except Exception as exc:
            self._render_status(frame, f"Face error: {exc}", (0, 0, 255))
            return

        endpoint = f"{self.config.api_url}/{self.config.action.lstrip('/')}"
        try:
            response = requests.post(
                endpoint,
                json={
                    "class_id": self.config.class_id,
                    "device_id": self.config.device_id,
                    "embedding": embedding,
                },
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
        except RequestException as exc:
            self._render_status(frame, f"Server error: {exc}", (0, 0, 255))
            return
        except ValueError:
            self._render_status(frame, "Invalid server response.", (0, 0, 255))
            return

        if payload.get("success"):
            self._render_status(frame, payload.get("student_name", "Matched"), (0, 180, 0))
        else:
            self._render_status(frame, payload.get("message", "Recognition failed."), (0, 0, 255))

    def extract_embedding(self, frame: np.ndarray) -> list[float]:
        deepface = load_deepface()
        representations = deepface.represent(
            img_path=frame,
            model_name=self.config.face_model,
            detector_backend="opencv",
            enforce_detection=True,
        )
        if not representations:
            raise ValueError("No face detected.")
        embedding = np.asarray(representations[0]["embedding"][: self.config.embedding_dim], dtype=np.float32)
        norm = np.linalg.norm(embedding)
        if norm:
            embedding = embedding / norm
        return embedding.tolist()

    def _render_status(self, frame: np.ndarray | None, message: str, color: tuple[int, int, int]) -> None:
        canvas = frame.copy() if frame is not None else np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(canvas, (20, 20), (620, 100), (20, 20, 20), -1)
        cv2.putText(canvas, message, (35, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)
        cv2.imshow("SmartAttend Kiosk", canvas)
        cv2.waitKey(1800)


if __name__ == "__main__":
    load_env_file()
    SmartAttendKiosk(KioskConfig()).run()
