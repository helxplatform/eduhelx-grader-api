import datetime
import unittest
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from app.services import AssignmentService, StudentAssignmentService
from app.models import AssignmentModel, StudentModel, ExtraTimeModel
from app.core.exceptions import (
    AssignmentNotFoundException, 
    AssignmentNotOpenException,
    AssignmentNotCreatedException,
    AssignmentClosedException
)

class TestStudentAssignmentService(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_session = MagicMock()
        self.mock_student = MagicMock(spec=StudentModel)
        self.mock_assignment = MagicMock(spec=AssignmentModel)
        self.mock_extra_time_model = MagicMock(spec=ExtraTimeModel)
    
    def test_get_adjusted_available_date_without_extra_time(self):
        self.mock_assignment.available_date = datetime.datetime(2022, 1, 1)
        self.mock_session.query().filter().first.return_value = None

        student_assignment_service = StudentAssignmentService(
            session=self.mock_session,
            student=self.mock_student,
            assignment=self.mock_assignment
        )
        result = student_assignment_service.get_adjusted_available_date()

        self.assertEqual(result, datetime.datetime(2022, 1, 1))

    def test_get_adjusted_available_date_with_extra_time(self):
        self.mock_assignment.available_date = datetime.datetime(2022, 1, 1)
        self.mock_extra_time_model.deferred_time = datetime.timedelta(days=1)
        self.mock_session.query().filter().first.return_value = self.mock_extra_time_model

        student_assignment_service = StudentAssignmentService(
            session=self.mock_session,
            student=self.mock_student,
            assignment=self.mock_assignment
        )
        result = student_assignment_service.get_adjusted_available_date()

        expected_date = datetime.datetime(2022, 1, 2)
        self.assertEqual(result, expected_date)

    async def test_get_adjusted_due_date_without_due_date(self):
        self.mock_assignment.due_date = None

        student_assignment_service = StudentAssignmentService(
            session=self.mock_session,
            student=self.mock_student,
            assignment=self.mock_assignment
        )
        result = student_assignment_service.get_adjusted_due_date()

        self.assertEqual(result, None)

    def test_get_adjusted_due_date_with_extra_time(self):
        self.mock_assignment.due_date = datetime.datetime(2023, 1, 1)
        self.mock_extra_time_model.deferred_time = datetime.timedelta(days=1)
        self.mock_extra_time_model.extra_time = datetime.timedelta(days=1)
        self.mock_student.base_extra_time = datetime.timedelta(days=1)
        self.mock_session.query().filter().first.return_value = self.mock_extra_time_model

        student_assignment_service = StudentAssignmentService(
            session=self.mock_session,
            student=self.mock_student,
            assignment=self.mock_assignment
        )
        result = student_assignment_service.get_adjusted_due_date()

        expected_date = datetime.datetime(2023, 1, 4)
        self.assertEqual(result, expected_date)

    def test_get_adjusted_due_date_without_extra_time(self):
        self.mock_assignment.due_date = datetime.datetime(2023, 1, 1)
        self.mock_student.base_extra_time = datetime.timedelta(days=1)
        self.mock_session.query().filter().first.return_value = None

        student_assignment_service = StudentAssignmentService(
            session=self.mock_session,
            student=self.mock_student,
            assignment=self.mock_assignment
        )
        result = student_assignment_service.get_adjusted_due_date()

        expected_date = datetime.datetime(2023, 1, 2)
        self.assertEqual(result, expected_date)

    #Testing get_is_available & get_is_closed when assignment is not created
    def test_assignment_not_created(self):
        self.mock_assignment.is_published = False

        student_assignment_service = StudentAssignmentService(
            session=self.mock_session,
            student=self.mock_student,
            assignment=self.mock_assignment
        )

        result_is_available = student_assignment_service._get_is_available()
        result_is_closed = student_assignment_service._get_is_closed()

        self.assertEqual(result_is_available, False)
        self.assertEqual(result_is_closed, False)

    def test_get_is_available(self):
        self.mock_assignment.is_published = True
        self.mock_session.query().filter().first.return_value = None
        self.mock_student.base_extra_time = datetime.timedelta(days=0)
        
        # available_date is in the past, the due_date is in the future, and the scalar is in the middle
        # allows us to test the get_is_available method & the get_adjusted_available_date method at once
        self.mock_assignment.available_date = datetime.datetime(2022, 1, 1)
        self.mock_assignment.due_date = datetime.datetime(2024, 1, 2)
        self.mock_session.scalar.return_value = datetime.datetime(2023, 1, 2)

        student_assignment_service = StudentAssignmentService(
            session=self.mock_session,
            student=self.mock_student,
            assignment=self.mock_assignment
        )
        result_get_is_available = student_assignment_service._get_is_available()
        result_get_is_closed = student_assignment_service._get_is_closed()

        self.assertEqual(result_get_is_available, True)
        self.assertEqual(result_get_is_closed, False)

        # available_date is in the future, the due_date is in the past, and the scalar is in the middle
        self.mock_assignment.available_date = datetime.datetime(2024, 1, 1)
        self.mock_assignment.due_date = datetime.datetime(2022, 1, 2)
        self.mock_session.scalar.return_value = datetime.datetime(2023, 1, 2)

        result_get_is_available = student_assignment_service._get_is_available()
        result_get_is_closed = student_assignment_service._get_is_closed()

        self.assertEqual(result_get_is_available, False)
        self.assertEqual(result_get_is_closed, True)

    def test_validate_student_can_submit(self):
        self.mock_assignment.is_published = False

        student_assignment_service = StudentAssignmentService(
            session=self.mock_session,
            student=self.mock_student,
            assignment=self.mock_assignment
        )

        with self.assertRaises(AssignmentNotCreatedException):
            student_assignment_service.validate_student_can_submit()

    def test_validate_student_can_submit_not_open(self):
        self.mock_assignment.is_published = True
        self.mock_session.query().filter().first.return_value = None
        self.mock_student.base_extra_time = datetime.timedelta(days=0)
        
        # available_date is in the future, the due_date is in the past, and the scalar is in the middle
        # allows us to test the get_is_available method & the get_adjusted_available_date method at once
        self.mock_assignment.available_date = datetime.datetime(2024, 1, 1)
        self.mock_session.scalar.return_value = datetime.datetime(2023, 1, 2)

        student_assignment_service = StudentAssignmentService(
            session=self.mock_session,
            student=self.mock_student,
            assignment=self.mock_assignment
        )

        with self.assertRaises(AssignmentNotOpenException):
            student_assignment_service.validate_student_can_submit()

    def test_validate_student_can_submit_closed(self):
        self.mock_assignment.is_published = True
        self.mock_session.query().filter().first.return_value = None
        self.mock_student.base_extra_time = datetime.timedelta(days=0)
        
        # available_date is in the past, the due_date is in the past, and the scalar is in the future
        # allows us to test the get_is_closed method & the get_adjusted_due_date method at once
        self.mock_assignment.available_date = datetime.datetime(2022, 1, 1)
        self.mock_assignment.due_date = datetime.datetime(2022, 6, 2)
        self.mock_session.scalar.return_value = datetime.datetime(2023, 1, 2)

        student_assignment_service = StudentAssignmentService(
            session=self.mock_session,
            student=self.mock_student,
            assignment=self.mock_assignment
        )

        with self.assertRaises(AssignmentClosedException):
            student_assignment_service.validate_student_can_submit()


suite = unittest.TestLoader().loadTestsFromTestCase(TestStudentAssignmentService)
unittest.TextTestRunner(verbosity=2).run(suite)
