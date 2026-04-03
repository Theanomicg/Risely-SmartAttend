from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FaceAssignment:
    student_index: int
    face_index: int
    confidence: float


def assign_face_matches(
    student_embeddings: Sequence[Sequence[Sequence[float]]],
    observed_embeddings: Sequence[Sequence[float]],
    *,
    threshold: float,
) -> list[FaceAssignment]:
    if not student_embeddings or not observed_embeddings:
        return []

    face_matrix = np.asarray(observed_embeddings, dtype=np.float32)
    if face_matrix.ndim == 1:
        face_matrix = face_matrix.reshape(1, -1)

    embedding_blocks: list[np.ndarray] = []
    owner_indices: list[int] = []
    for student_index, embeddings in enumerate(student_embeddings):
        embedding_matrix = np.asarray(embeddings, dtype=np.float32)
        if embedding_matrix.size == 0:
            continue
        if embedding_matrix.ndim == 1:
            embedding_matrix = embedding_matrix.reshape(1, -1)
        embedding_blocks.append(embedding_matrix)
        owner_indices.extend([student_index] * embedding_matrix.shape[0])

    if not embedding_blocks:
        return []

    stored_embeddings = np.vstack(embedding_blocks)
    similarity_by_embedding = stored_embeddings @ face_matrix.T
    similarity_by_student = np.full((len(student_embeddings), face_matrix.shape[0]), -1.0, dtype=np.float32)
    np.maximum.at(similarity_by_student, np.asarray(owner_indices, dtype=np.intp), similarity_by_embedding)

    candidate_positions = np.argwhere(similarity_by_student >= threshold)
    ranked_candidates = sorted(
        (
            (
                float(similarity_by_student[student_index, face_index]),
                int(student_index),
                int(face_index),
            )
            for student_index, face_index in candidate_positions
        ),
        reverse=True,
    )

    assignments: list[FaceAssignment] = []
    assigned_students: set[int] = set()
    assigned_faces: set[int] = set()
    for confidence, student_index, face_index in ranked_candidates:
        if student_index in assigned_students or face_index in assigned_faces:
            continue
        assigned_students.add(student_index)
        assigned_faces.add(face_index)
        assignments.append(
            FaceAssignment(
                student_index=student_index,
                face_index=face_index,
                confidence=confidence,
            )
        )

    return assignments
