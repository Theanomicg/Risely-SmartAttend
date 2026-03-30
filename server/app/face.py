from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from app.config import get_settings


settings = get_settings()


def _load_deepface() -> Any:
    from deepface import DeepFace

    return DeepFace


def normalize_embedding(vector: list[float] | np.ndarray) -> list[float]:
    array = np.asarray(vector, dtype=np.float32)
    norm = np.linalg.norm(array)
    if norm == 0:
        return array.tolist()
    return (array / norm).tolist()


def extract_embeddings_from_image(image: np.ndarray) -> list[list[float]]:
    deepface = _load_deepface()
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    errors: list[str] = []
    for detector_backend in settings.detector_backend_list:
        try:
            representations = deepface.represent(
                img_path=rgb_image,
                model_name=settings.face_model_name,
                detector_backend=detector_backend,
                enforce_detection=True,
            )
            if representations:
                return [
                    normalize_embedding(representation["embedding"][: settings.embedding_dim])
                    for representation in representations
                ]
        except Exception as exc:
            errors.append(f"{detector_backend}: {exc}")

    raise ValueError("No face detected in image.")


def extract_embedding_from_image(image: np.ndarray) -> list[float]:
    return extract_embeddings_from_image(image)[0]


def extract_embeddings_from_bytes(images: list[bytes]) -> tuple[list[list[float]], list[str]]:
    embeddings: list[list[float]] = []
    failures: list[str] = []
    for index, raw in enumerate(images, start=1):
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            failures.append(f"Photo {index}: unreadable image file.")
            continue
        try:
            embeddings.append(extract_embedding_from_image(image))
        except ValueError as exc:
            failures.append(f"Photo {index}: {exc}")
    return embeddings, failures


def cosine_similarity(a: list[float], b: list[float]) -> float:
    vec_a = np.asarray(a, dtype=np.float32)
    vec_b = np.asarray(b, dtype=np.float32)
    denom = np.linalg.norm(vec_a) * np.linalg.norm(vec_b)
    if denom == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / denom)
