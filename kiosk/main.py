from __future__ import annotations

import os
from dataclasses import dataclass

import cv2
import numpy as np
import requests
from requests import RequestException


def load_deepface():
    from deepface import DeepFace

    return DeepFace


@dataclass
class KioskConfig:
    api_url: str = os.getenv("SMARTATTEND_API_URL", "http://localhost:8000")
    classroom_id: str = os.getenv("SMARTATTEND_CLASSROOM_ID", "classroom-a")
    device_id: str = os.getenv("SMARTATTEND_DEVICE_ID", "pi-kiosk-01")
    camera_source: str = os.getenv("SMARTATTEND_CAMERA_SOURCE", "0")
    action: str = os.getenv("SMARTATTEND_ACTION", "checkin")
    face_model: str = os.getenv("SMARTATTEND_FACE_MODEL", "ArcFace")
    embedding_dim: int = int(os.getenv("SMARTATTEND_EMBEDDING_DIM", "128"))


class SmartAttendKiosk:
    def __init__(self, config: KioskConfig) -> None:
        self.config = config
        source = int(config.camera_source) if config.camera_source.isdigit() else config.camera_source
        self.capture = cv2.VideoCapture(source)

    def run(self) -> None:
        while True:
            ok, frame = self.capture.read()
            if not ok:
                self._render_status(None, "Camera read failed.", (0, 0, 255))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

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
                    "classroom_id": self.config.classroom_id,
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
    SmartAttendKiosk(KioskConfig()).run()
