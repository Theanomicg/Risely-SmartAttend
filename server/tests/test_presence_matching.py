from __future__ import annotations

import sys
import unittest
from unittest.mock import AsyncMock, Mock
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.services.matching import find_best_student_match  # noqa: E402
from app.services.presence import assign_face_matches  # noqa: E402


class AssignFaceMatchesTests(unittest.TestCase):
    def test_competing_students_do_not_share_one_face(self) -> None:
        assignments = assign_face_matches(
            student_embeddings=[
                [[1.0, 0.0]],
                [[0.95, 0.05]],
            ],
            observed_embeddings=[[1.0, 0.0]],
            threshold=0.7,
        )

        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0].student_index, 0)
        self.assertEqual(assignments[0].face_index, 0)

    def test_distinct_faces_match_distinct_students(self) -> None:
        assignments = assign_face_matches(
            student_embeddings=[
                [[1.0, 0.0]],
                [[0.0, 1.0]],
            ],
            observed_embeddings=[
                [1.0, 0.0],
                [0.0, 1.0],
            ],
            threshold=0.7,
        )

        self.assertEqual(
            {(assignment.student_index, assignment.face_index) for assignment in assignments},
            {(0, 0), (1, 1)},
        )

    def test_ignores_faces_below_threshold(self) -> None:
        assignments = assign_face_matches(
            student_embeddings=[[[1.0, 0.0]]],
            observed_embeddings=[[0.1, 0.1]],
            threshold=0.7,
        )

        self.assertEqual(assignments, [])


class FindBestStudentMatchQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_class_scoped_match_uses_typed_where_clause(self) -> None:
        session = AsyncMock()
        execute_result = Mock()
        execute_result.mappings.return_value.first.return_value = None
        session.execute.return_value = execute_result

        await find_best_student_match(session, [0.0] * 128, class_id="class-10-a")

        sql = str(session.execute.await_args.args[0])
        params = session.execute.await_args.args[1]
        self.assertIn("WHERE s.class_id = :class_id", sql)
        self.assertNotIn(":class_id IS NULL", sql)
        self.assertEqual(params["class_id"], "class-10-a")

    async def test_unscoped_match_does_not_bind_class_id(self) -> None:
        session = AsyncMock()
        execute_result = Mock()
        execute_result.mappings.return_value.first.return_value = None
        session.execute.return_value = execute_result

        await find_best_student_match(session, [0.0] * 128)

        sql = str(session.execute.await_args.args[0])
        params = session.execute.await_args.args[1]
        self.assertNotIn("WHERE s.class_id = :class_id", sql)
        self.assertNotIn("class_id", params)


if __name__ == "__main__":
    unittest.main()
