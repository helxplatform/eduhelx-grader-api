import json
from typing import List
from pydantic import PositiveInt
from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.exceptions.assignment import AssignmentCannotBeUnpublished
from app.events import dispatch
from app.models import AssignmentModel, InstructorModel, StudentModel, ExtraTimeModel
from app.models.course import CourseModel
from app.schemas import AssignmentSchema, InstructorAssignmentSchema, StudentAssignmentSchema, UpdateAssignmentSchema
from app.events import CreateAssignmentCrudEvent, ModifyAssignmentCrudEvent, DeleteAssignmentCrudEvent
from app.core.exceptions import (
    AssignmentNotFoundException,
    AssignmentNotPublishedException,
    AssignmentNotOpenException,
    AssignmentClosedException,
    AssignmentDueBeforeOpenException,
    SubmissionMaxAttemptsReachedException
)
from app.enums.assignment_status import AssignmentStatus
from app.services.submission_service import SubmissionService

class AssignmentService:
    def __init__(self, session: Session):
        self.session = session
        
    async def create_assignment(
        self,
        id: int,
        name: str,
        directory_path: str,
        max_attempts: PositiveInt | None,
        available_date: datetime | None,
        due_date: datetime | None,
        is_published: bool
    ) -> AssignmentModel:
        from app.services import GiteaService, FileOperation, FileOperationType, CourseService

        if available_date is not None and due_date is not None and available_date >= due_date:
            raise AssignmentDueBeforeOpenException

        gitea_service = GiteaService(self.session)
        course_service = CourseService(self.session)

        assignment = AssignmentModel(
            id=id,
            name=name,
            directory_path=directory_path,
            # This is relative to directory_path
            master_notebook_path=f"{ name }.ipynb",
            max_attempts=max_attempts,
            available_date=available_date,
            due_date=due_date,
            is_published=is_published
        )

        self.session.add(assignment)
        self.session.commit()

        master_repository_name = await course_service.get_master_repository_name()
        owner = await course_service.get_instructor_gitea_organization_name()
        branch_name = await course_service.get_master_branch_name()

        master_notebook_path = f"{ assignment.directory_path }/{ assignment.master_notebook_path }"
        # Default empty notebook for JupyterLab 4 w/ Otter Config
        otter_config_cell = {
            "cell_type": "raw",
            "metadata": {},
            "source": [
                "# ASSIGNMENT CONFIG\n",
                "requirements: requirements.txt\n"
                "export_cell: false\n"
            ]
        }
        title_cell = {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                f"# { assignment.name }\n",
            ]
        }
        
        # See comment above commented out FileOperation below
        # master_notebook_content = json.dumps({ "cells": [otter_config_cell, title_cell], "metadata": {  "kernelspec": {   "display_name": "Python 3 (ipykernel)",   "language": "python",   "name": "python3"  },  "language_info": {   "codemirror_mode": {    "name": "ipython",    "version": 3   },   "file_extension": ".py",   "mimetype": "text/x-python",   "name": "python",   "nbconvert_exporter": "python",   "pygments_lexer": "ipython3",   "version": "3.11.5"  } }, "nbformat": 4, "nbformat_minor": 5})

        gitignore_path = f"{ directory_path }/.gitignore"
        gitignore_content = await self.get_gitignore_content(assignment)
        
        readme_path = f"{ directory_path }/README.md"
        readme_content = f"# { name }"

        requirements_path = f"{ directory_path }/requirements.txt"
        requirements_content = f"otter-grader==5.5.0"

        files_to_modify = [
            # Until toggleable workahead on assignments is implemented, there's no point in creating a master notebook
            # for professors since they will need to make a new one to edit it anyways per the merge control policy.
            # FileOperation(content=master_notebook_content, path=master_notebook_path, operation=FileOperationType.CREATE),
            FileOperation(content=gitignore_content, path=gitignore_path, operation=FileOperationType.CREATE),
            FileOperation(content=readme_content, path=readme_path, operation=FileOperationType.CREATE),
            FileOperation(content=requirements_content, path=requirements_path, operation=FileOperationType.CREATE)
        ]
        
        try:
            await gitea_service.modify_repository_files(
                name=master_repository_name,
                owner=owner,
                branch_name=branch_name,
                commit_message="Initialize assignment",
                files=files_to_modify
            )
        except Exception as e:
            self.session.delete(assignment)
            self.session.commit()
            raise e

        dispatch(CreateAssignmentCrudEvent(assignment=assignment))

        return assignment
    
    async def delete_assignment(self, assignment: AssignmentModel) -> None:
        from app.services import GiteaService, CourseService, FileOperation, FileOperationType

        gitea_service = GiteaService(self.session)
        course_service = CourseService(self.session)

        master_repository_name = await course_service.get_master_repository_name()
        owner = await course_service.get_instructor_gitea_organization_name()
        branch_name = await course_service.get_master_branch_name()
        directory_path = assignment.directory_path

        files_to_modify = [
            FileOperation(content="", path=f"{ directory_path }", operation=FileOperationType.DELETE)
        ]

        """ (maybe) this can come back in the future.
        But it violates the merge control policy if active, which is problematic at the moment."""
        # await gitea_service.modify_repository_files(
        #     name=master_repository_name,
        #     owner=owner,
        #     branch_name=branch_name,
        #     commit_message=f"Delete assignment",
        #     files=files_to_modify
        # )

        self.session.delete(assignment)
        self.session.commit()

        dispatch(DeleteAssignmentCrudEvent(assignment=assignment))

    async def get_assignment_by_id(self, id: int) -> AssignmentModel:
        assignment = self.session.query(AssignmentModel) \
            .filter_by(id=id) \
            .first()
        if assignment is None:
            raise AssignmentNotFoundException()
        return assignment

    async def get_assignments(self) -> List[AssignmentModel]:
        return self.session.query(AssignmentModel) \
            .all()
    
    async def get_assignment_by_name(self, name: str) -> AssignmentModel:
        assignment = self.session.query(AssignmentModel) \
            .filter_by(name=name) \
            .first()
        if assignment is None:
            raise AssignmentNotFoundException()
        return assignment
    
    async def update_assignment(
            self, 
            assignment: AssignmentModel, 
            update_assignment: UpdateAssignmentSchema, 
            student_id: int | None = None
    ) -> AssignmentModel:
        from app.services.lms_sync_service import LmsSyncService

        update_fields = update_assignment.dict(exclude_unset=True)
        
        if "name" in update_fields:
            assignment.name = update_fields["name"]

        if "directory_path" in update_fields:
            assignment.directory_path = update_fields["directory_path"]

        if "master_notebook_path" in update_fields:
            assignment.master_notebook_path = update_fields["master_notebook_path"]

        if "grader_question_feedback" in update_fields:
            assignment.grader_question_feedback = update_fields["grader_question_feedback"]

        if "max_attempts" in update_fields:
            assignment.max_attempts = update_fields["max_attempts"]

        if "available_date" in update_fields:
            assignment.available_date = update_fields["available_date"]
        
        if "due_date" in update_fields:
            assignment.due_date = update_fields["due_date"]

        if "is_published" in update_fields:
            if update_fields["is_published"] == False:
                canvas_assignment = await LmsSyncService(self.session).get_assignment(assignment.id)
                if canvas_assignment["unpublishable"] == False:
                    raise AssignmentCannotBeUnpublished("Canvas is not allowing this assignment to be unpublished")
            assignment.is_published = update_fields["is_published"]

        if assignment.available_date is not None and assignment.due_date is not None and assignment.available_date >= assignment.due_date:
            raise AssignmentDueBeforeOpenException()

        await LmsSyncService(self.session).upsync_assignment(assignment)
        
        self.session.commit()

        dispatch(ModifyAssignmentCrudEvent(assignment=assignment, modified_fields=list(update_fields.keys())))

        return assignment
    
    # Get the earliest time at which the given assignment is available
    async def get_earliest_available_date(self, assignment: AssignmentModel) -> datetime | None:
        if assignment.available_date is None: return None
        earliest_deferral = self.session.query(ExtraTimeModel.deferred_time) \
            .filter_by(assignment_id=assignment.id) \
            .order_by(ExtraTimeModel.deferred_time) \
            .first()
        
        return assignment.available_date + (earliest_deferral if earliest_deferral is not None else timedelta(0))
    
    # Gets the latest time at which the given assignment closes
    async def get_latest_due_date(self, assignment: AssignmentModel) -> datetime | None:
        if assignment.due_date is None: return None
        latest_time = self.session.query(ExtraTimeModel.extra_time) \
            .filter_by(assignment_id=assignment.id) \
            .order_by(ExtraTimeModel.extra_time.desc()) \
            .first()
        
        return assignment.due_date + (latest_time.extra_time if latest_time.extra_time is not None else timedelta(0))

    """ Compute the default gitignore for an assignment. """
    async def get_gitignore_content(self, assignment: AssignmentModel) -> str:
        protected_files_str = "\n".join(await self.get_protected_files(assignment))

        return f"""### Defaults ###
__pycache__/
*.py[cod]
*$py.class
*venv
.ipynb_checkpoints
.OTTER_LOG
*~backup
.nfs*

### Protected ###
{ protected_files_str }
"""
    
    """
    NOTE: File paths are not necessarily real files and may instead be globs.
    NOTE: File paths are relative to `assignment.directory_path`.
    """
    async def get_protected_files(self, assignment: AssignmentModel) -> list[str]:
        return [
            "*grades.csv",
            "*grading_config.json",
            assignment.master_notebook_path,
            f"{ assignment.name }-dist",
            "**/.ssh",
            "prof-scripts"
        ]
    
    """
    NOTE: File paths are not necessarily real files and may instead be globs.
    NOTE: File paths are relative to `assignment.directory_path`
    """
    async def get_overwritable_files(self, assignment: AssignmentModel) -> list[str]:
        return [
            "README.md",
            "helpers.*",
            "requirements.txt",
            "instruction*.txt",
            ".gitignore",
        ]
    
    async def get_master_notebook_name(self, assignment: AssignmentModel) -> str:
        return self._compute_master_notebook_name(assignment.name)
    
    @staticmethod
    def _compute_master_notebook_name(assignment_name: str) -> str:
        return f"{ assignment_name }-prof.ipynb"

class InstructorAssignmentService(AssignmentService):
    def __init__(self, session: Session, instructor_model: InstructorModel, assignment_model: AssignmentModel, course_model: CourseModel):
        super().__init__(session)
        self.instructor_model = instructor_model
        self.assignment_model = assignment_model
        self.course_model = course_model 

    # The release date for a specific student, considering extra_time
    def get_adjusted_available_date(self) -> datetime | None:
        assignment_open_date = self.assignment_model.available_date or self.course_model.start_at
        if assignment_open_date is None: return None
        
        return assignment_open_date

    # The due date for a specific student, considering extra_time
    def get_adjusted_due_date(self) -> datetime | None:
        assignment_due_date = self.assignment_model.due_date or self.course_model.end_at
        if assignment_due_date is None: return None

        return assignment_due_date

    def get_assignment_status(self) -> AssignmentStatus:
        if not self.assignment_model.is_published: return AssignmentStatus.UNPUBLISHED

        current_timestamp = self.session.scalar(func.current_timestamp())
        adjusted_available_date = self.get_adjusted_available_date()
        adjusted_due_date = self.get_adjusted_due_date()

        # Until a course is properly configured (has start_at,end_at dates),
        # all published assignments will display as upcoming. 
        if adjusted_available_date is None or adjusted_due_date is None:
            return AssignmentStatus.UPCOMING
        
        if adjusted_available_date >= current_timestamp: return AssignmentStatus.UPCOMING

        if adjusted_due_date > current_timestamp: return AssignmentStatus.OPEN
        else: return AssignmentStatus.CLOSED
    
    async def get_instructor_assignment_schema(self) -> InstructorAssignmentSchema:
        assignment = AssignmentSchema.from_orm(self.assignment_model).dict()

        assignment["protected_files"] = await self.get_protected_files(self.assignment_model)
        assignment["overwritable_files"] = await self.get_overwritable_files(self.assignment_model)

        assignment_status = self.get_assignment_status()
        assignment["status"] = assignment_status.value
        assignment["is_available"] = assignment_status == AssignmentStatus.OPEN
        assignment["is_closed"] = assignment_status == AssignmentStatus.CLOSED
        assignment["is_published"] = assignment_status != AssignmentStatus.UNPUBLISHED

        return InstructorAssignmentSchema(**assignment)
    
class StudentAssignmentService(AssignmentService):
    def __init__(self, session: Session, student_model: StudentModel, assignment_model: AssignmentModel, course_model: CourseModel):
        super().__init__(session)
        self.student_model = student_model
        self.assignment_model = assignment_model
        self.course_model = course_model
        self.extra_time_model = self._get_extra_time_model()

    def _get_extra_time_model(self) -> ExtraTimeModel | None:
        extra_time_model = self.session.query(ExtraTimeModel) \
            .filter(
                (ExtraTimeModel.assignment_id == self.assignment_model.id) &
                (ExtraTimeModel.student_id == self.student_model.id)
            ) \
            .first()
        return extra_time_model

    # The release date for a specific student, considering extra_time
    def get_adjusted_available_date(self) -> datetime | None:
        assignment_open_date = self.assignment_model.available_date or self.course_model.start_at
        if assignment_open_date is None: return None
        deferred_time = self.extra_time_model.deferred_time if self.extra_time_model is not None else timedelta(0)
        
        return assignment_open_date + deferred_time

    # The due date for a specific student, considering extra_time
    def get_adjusted_due_date(self) -> datetime | None:
        assignment_due_date = self.assignment_model.due_date or self.course_model.end_at
        if assignment_due_date is None: return None

        # If a student does not have any extra time allotted for the assignment,
        # allocate them a timedelta of 0.
        if self.extra_time_model is not None:
            deferred_time = self.extra_time_model.deferred_time
            extra_time = self.extra_time_model.extra_time
        else:
            deferred_time = timedelta(0)
            extra_time = timedelta(0)

        # Base due date + have to defer by whatever amount the available date was deferred by + extra time + base extra time
        return assignment_due_date + deferred_time + extra_time + self.student_model.base_extra_time

    def _get_is_available(self) -> bool:
        adjusted_available_date = self.get_adjusted_available_date()
        if adjusted_available_date is None: return True
        current_timestamp = self.session.scalar(func.current_timestamp())
        return current_timestamp >= adjusted_available_date
    
    def _get_is_closed(self) -> bool:
        adjusted_due_date = self.get_adjusted_due_date()
        if adjusted_due_date is None: 
            return not self._get_is_available()
        current_timestamp = self.session.scalar(func.current_timestamp())
        return current_timestamp > adjusted_due_date
    
    def get_assignment_status(self) -> AssignmentStatus:
        if not self.assignment_model.is_published: return AssignmentStatus.UNPUBLISHED

        current_timestamp = self.session.scalar(func.current_timestamp())
        adjusted_available_date = self.get_adjusted_available_date()
        adjusted_due_date = self.get_adjusted_due_date()

        # Until a course is properly configured (has start_at,end_at dates),
        # all published assignments will display as upcoming. 
        if adjusted_available_date is None or adjusted_due_date is None:
            return AssignmentStatus.UPCOMING
        
        if adjusted_available_date >= current_timestamp: return AssignmentStatus.UPCOMING

        if adjusted_due_date > current_timestamp: return AssignmentStatus.OPEN
        else: return AssignmentStatus.CLOSED

    async def validate_student_can_submit(self):
        assignment_status = self.get_assignment_status()
        if assignment_status == AssignmentStatus.UNPUBLISHED:
            raise AssignmentNotPublishedException()

        if assignment_status == AssignmentStatus.UPCOMING:
            raise AssignmentNotOpenException()

        if assignment_status == AssignmentStatus.CLOSED:
            raise AssignmentClosedException()
        
        if self.assignment_model.max_attempts is not None:
            attempts = await SubmissionService(self.session).get_current_submission_attempt(self.student_model, self.assignment_model)
            if attempts >= self.assignment_model.max_attempts:
                raise SubmissionMaxAttemptsReachedException()

    async def get_student_assignment_schema(self) -> StudentAssignmentSchema:
        assignment = AssignmentSchema.from_orm(self.assignment_model).dict()
        assignment_status = self.get_assignment_status()

        assignment["protected_files"] = await self.get_protected_files(self.assignment_model)
        assignment["overwritable_files"] = await self.get_overwritable_files(self.assignment_model)
        assignment["current_attempts"] = await SubmissionService(self.session).get_current_submission_attempt(
            self.student_model,
            self.assignment_model
        )
        assignment["status"] = assignment_status.value
        assignment["adjusted_available_date"] = self.get_adjusted_available_date()
        assignment["adjusted_due_date"] = self.get_adjusted_due_date()
        assignment["is_available"] = assignment_status == AssignmentStatus.OPEN
        assignment["is_closed"] = assignment_status == AssignmentStatus.CLOSED
        assignment["is_published"] = assignment_status != AssignmentStatus.UNPUBLISHED
        assignment["is_deferred"] = assignment["adjusted_available_date"] != assignment["available_date"]
        assignment["is_extended"] = assignment["adjusted_due_date"] != assignment["due_date"]

        return StudentAssignmentSchema(**assignment)