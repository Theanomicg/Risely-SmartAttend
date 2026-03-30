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
    representations = deepface.represent(
        img_path=image,
        model_name=settings.face_model_name,
        detector_backend="opencv",
        enforce_detection=True,
    )
    if not representations:
        raise ValueError("No face detected in image.")
    return [
        normalize_embedding(representation["embedding"][: settings.embedding_dim])
        for representation in representations
    ]


def extract_embedding_from_image(image: np.ndarray) -> list[float]:
    return extract_embeddings_from_image(image)[0]


def extract_embeddings_from_bytes(images: list[bytes]) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for raw in images:
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            continue
        embeddings.append(extract_embedding_from_image(image))
    return embeddings


def cosine_similarity(a: list[float], b: list[float]) -> float:
    vec_a = np.asarray(a, dtype=np.float32)
    vec_b = np.asarray(b, dtype=np.float32)
    denom = np.linalg.norm(vec_a) * np.linalg.norm(vec_b)
    if denom == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / denom)
