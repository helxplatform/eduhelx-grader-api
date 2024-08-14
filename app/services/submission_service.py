from typing import List
from datetime import datetime
from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from app.events import dispatch
from app.models import StudentModel, AssignmentModel, SubmissionModel, CourseModel
from app.core.exceptions import SubmissionNotFoundException
from app.core.utils.datetime import get_now_with_tzinfo
from app.models.course import CourseModel
from app.services import StudentService
from app.schemas import SubmissionSchema, DatabaseSubmissionSchema
from app.events import CreateSubmissionCrudEvent, ModifySubmissionCrudEvent, DeleteSubmissionCrudEvent
from app.services.course_service import CourseService

class SubmissionService:
    def __init__(self, session: Session):
        self.session = session

    async def create_submission(
        self,
        student: StudentModel,
        assignment: AssignmentModel,
        commit_id: str
    ) -> SubmissionModel:
        # TODO: We should validate that the submitted commit id actually exists in gitea before persisting it in the database.
        # We don't want another component of EduHeLx to assume the commit we return exists and crash when it doesn't.
        # Alternatively, we could bake this logic into the endpoints to get submissions, rather than into this one.

        course = await CourseService(self.session).get_course()

        from app.services import StudentAssignmentService

        # Assert the assignment can be submitted to by the student.
        await StudentAssignmentService(self.session, student, assignment, course).validate_student_can_submit()

        submission = SubmissionModel(
            student_id=student.id,
            assignment_id=assignment.id,
            commit_id=commit_id
        )

        self.session.add(submission)
        self.session.commit()

        dispatch(CreateSubmissionCrudEvent(submission=submission))

        return submission
    
    async def get_submission_by_id(
        self,
        submission_id: int
    ) -> SubmissionModel:
        submission = self.session.query(SubmissionModel) \
            .filter_by(id=submission_id) \
            .first()
        if submission is None:
            raise SubmissionNotFoundException()
        return submission

    async def get_submissions(
        self,
        student: StudentModel,
        assignment: AssignmentModel
    ) -> List[SubmissionModel]:
        submissions = self.session.query(SubmissionModel) \
            .filter_by(student_id=student.id, assignment_id=assignment.id) \
            .order_by(desc(SubmissionModel.submission_time)) \
            .all()

        return submissions

    async def get_active_submission(
        self,
        student: StudentModel,
        assignment: AssignmentModel,
        moment: datetime | None = None
    ) -> SubmissionModel:
        if moment is None: moment = get_now_with_tzinfo()
        submission = self.session.query(SubmissionModel) \
            .filter_by(student_id=student.id, assignment_id=assignment.id) \
            .filter(SubmissionModel.submission_time <= moment) \
            .order_by(desc(SubmissionModel.submission_time)) \
            .limit(1) \
            .first()
        if submission is None:
            raise SubmissionNotFoundException()
        return submission
        
    """ NOTE: Marked for refactor. Not a fan of this workflow... """
    async def get_current_submission_attempt(
        self,
        student: StudentModel,
        assignment: AssignmentModel
    ) -> int:
        student_submissions = self.session.query(SubmissionModel) \
            .filter(SubmissionModel.assignment_id == assignment.id) \
            .filter(SubmissionModel.student_id == student.id)
        return student_submissions.count()
        
    async def get_submission_schema(self, submission: SubmissionModel) -> SubmissionSchema:
        submission_schema = DatabaseSubmissionSchema.from_orm(submission).dict()
        submission_schema["active"] = await self.get_active_submission(submission.student, submission.assignment) == submission
        
        return SubmissionSchema(**submission_schema)
