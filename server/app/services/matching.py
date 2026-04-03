from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings


settings = get_settings()


@dataclass
class MatchResult:
    uid: str | None
    student_name: str | None
    confidence: float | None
    distance: float | None


def to_pgvector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"


async def find_best_student_match(
    session: AsyncSession,
    embedding: list[float],
    *,
    class_id: str | None = None,
) -> MatchResult:
    sql_params = {"embedding": to_pgvector_literal(embedding)}
    sql = text(
        """
        SELECT
            s.uid,
            s.name,
            (1 - (stored_embedding <=> CAST(:embedding AS vector))) AS confidence,
            (stored_embedding <=> CAST(:embedding AS vector)) AS distance
        FROM students s
        CROSS JOIN LATERAL unnest(s.face_embeddings) AS stored_embedding
        ORDER BY stored_embedding <=> CAST(:embedding AS vector)
        LIMIT 1
        """
    )
    if class_id is not None:
        sql = text(
            """
            SELECT
                s.uid,
                s.name,
                (1 - (stored_embedding <=> CAST(:embedding AS vector))) AS confidence,
                (stored_embedding <=> CAST(:embedding AS vector)) AS distance
            FROM students s
            CROSS JOIN LATERAL unnest(s.face_embeddings) AS stored_embedding
            WHERE s.class_id = :class_id
            ORDER BY stored_embedding <=> CAST(:embedding AS vector)
            LIMIT 1
            """
        )
        sql_params["class_id"] = class_id

    result = await session.execute(sql, sql_params)
    row = result.mappings().first()
    if not row:
        return MatchResult(uid=None, student_name=None, confidence=None, distance=None)

    confidence = float(row["confidence"])
    distance = float(row["distance"])
    if distance > settings.face_distance_threshold:
        return MatchResult(uid=None, student_name=None, confidence=confidence, distance=distance)

    return MatchResult(
        uid=row["uid"],
        student_name=row["name"],
        confidence=confidence,
        distance=distance,
    )
