from typing import List
from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.events import event_emitter
from app.models import AssignmentModel, InstructorModel, StudentModel, ExtraTimeModel
from app.schemas import AssignmentSchema, InstructorAssignmentSchema, StudentAssignmentSchema, UpdateAssignmentSchema
from app.events import CreateAssignmentCrudEvent, ModifyAssignmentCrudEvent, DeleteAssignmentCrudEvent
from app.core.exceptions import (
    AssignmentNotFoundException,
    AssignmentNotCreatedException,
    AssignmentNotOpenException,
    AssignmentClosedException,
    AssignmentDueBeforeOpenException,
    AssignmentNameTakenException,
    DatabaseTransactionException
)

class AssignmentService:
    def __init__(self, session: Session):
        self.session = session
        
    async def create_assignment(
        self,
        id: int,
        name: str,
        directory_path: str,
        available_date: datetime | None,
        due_date: datetime | None
    ) -> AssignmentModel:
        from app.services import GiteaService, FileOperation, FileOperationType, CourseService

        if available_date is not None and due_date is not None and available_date >= due_date:
            raise AssignmentDueBeforeOpenException
        
        try:
            await self.get_assignment_by_name(name)
            raise AssignmentNameTakenException()
        except AssignmentNotFoundException: pass

        gitea_service = GiteaService(self.session)
        course_service = CourseService(self.session)

        with self.session.begin_nested():
            assignment = AssignmentModel(
                id=id,
                name=name,
                directory_path=directory_path,
                available_date=available_date,
                due_date=due_date
            )

            self.session.add(assignment)
            try:
                self.session.flush()
            except SQLAlchemyError as e:
                DatabaseTransactionException.raise_exception(e)

            master_repository_name = await course_service.get_master_repository_name()
            owner = await course_service.get_instructor_gitea_organization_name()
            branch_name = await course_service.get_master_branch_name()

            master_notebook_name = await self.get_master_notebook_name(assignment)
            master_notebook_path = f"{ directory_path }/{ master_notebook_name }"
            # Default empty notebook for JupyterLab 4
            master_notebook_content = "{\n \"cells\": [],\n \"metadata\": {},\n \"nbformat\": 4,\n \"nbformat_minor\": 5\n}"

            gitignore_path = f"{ directory_path }/.gitignore"
            gitignore_content = await self.get_gitignore_content(assignment)
            
            readme_path = f"{ directory_path }/README.md"
            readme_content = f"# { name }"

            files_to_modify = [
                FileOperation(content=master_notebook_content, path=master_notebook_path, operation=FileOperationType.CREATE),
                FileOperation(content=gitignore_content, path=gitignore_path, operation=FileOperationType.CREATE),
                FileOperation(content=readme_content, path=readme_path, operation=FileOperationType.CREATE)
            ]

            await gitea_service.modify_repository_files(
                name=master_repository_name,
                owner=owner,
                branch_name=branch_name,
                commit_message="Initialize assignment",
                files=files_to_modify
            )

            try:
                """ BUG: HLXK-286. This dispatch needs to be cleaned up since it can raise. However,
                at the moment, there's no mechanism for us to undo the commit with. And we can't dispatch
                before the commit is pushed (inconsistent state). """
                await event_emitter.emit_async(CreateAssignmentCrudEvent(assignment=assignment))
            except:
                # TODO
                # For now, just pretend that everything is okay if an event handler fails.
                pass

        self.session.commit()
        return assignment
    
    async def delete_assignment(self, assignment: AssignmentModel) -> None:
        from app.services import GiteaService, CourseService, FileOperation, FileOperationType

        gitea_service = GiteaService(self.session)
        course_service = CourseService(self.session)

        with self.session.begin_nested():
            master_repository_name = await course_service.get_master_repository_name()
            owner = await course_service.get_instructor_gitea_organization_name()
            branch_name = await course_service.get_master_branch_name()
            directory_path = assignment.directory_path

            files_to_modify = [
                FileOperation(content="", path=f"{ directory_path }", operation=FileOperationType.DELETE)
            ]

            self.session.delete(assignment)
            try:
                self.session.flush()
            except SQLAlchemyError as e:
                DatabaseTransactionException.raise_exception(e)

            await gitea_service.modify_repository_files(
                name=master_repository_name,
                owner=owner,
                branch_name=branch_name,
                commit_message=f"Delete assignment",
                files=files_to_modify
            )
            
            try:
                await event_emitter.emit_async(DeleteAssignmentCrudEvent(assignment=assignment))
            except:
                # TODO
                # Needs cleanup, see same comment in create_assignment event dispatch
                pass
            
        self.session.commit()

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
    
    async def update_assignment(self, assignment: AssignmentModel, update_assignment: UpdateAssignmentSchema) -> AssignmentModel:
        update_fields = update_assignment.dict(exclude_unset=True)
        
        with self.session.begin_nested():
            if "name" in update_fields:
                assignment.name = update_fields["name"]

            if "directory_path" in update_fields:
                assignment.directory_path = update_fields["directory_path"]

            if "available_date" in update_fields:
                assignment.available_date = update_fields["available_date"]
            
            if "due_date" in update_fields:
                assignment.due_date = update_fields["due_date"]

            if assignment.available_date is not None and assignment.due_date is not None and assignment.available_date >= assignment.due_date:
                raise AssignmentDueBeforeOpenException

            try:
                self.session.flush()
            except SQLAlchemyError as e:
                DatabaseTransactionException.raise_exception(e)

            await event_emitter.emit_async(ModifyAssignmentCrudEvent(assignment=assignment, modified_fields=list(update_fields.keys())))

        self.session.commit()    
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
    
    async def get_master_notebook_name(self, assignment: AssignmentModel) -> str:
        return self._compute_master_notebook_name(assignment.name)
    
    @classmethod
    def _compute_master_notebook_name(cls, assignment_name: str) -> str:
        return f"{ assignment_name }-prof.ipynb"

    """ Compute the default gitignore for an assignment. """
    async def get_gitignore_content(self, assignment: AssignmentModel) -> str:
        master_notebook_name = await self.get_master_notebook_name(assignment)
        return f"""### Python ###
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

### Misc ###
*.DS_Store
*grades.csv
{ master_notebook_name }
{ assignment.name }-dist
.ssh
.ipynb_checkpoints
*venv
prof-scripts/*
"""

class InstructorAssignmentService(AssignmentService):
    def __init__(self, session: Session, instructor: InstructorModel, assignment: AssignmentModel):
        super().__init__(session)
        self.instructor = instructor
        self.assignment = assignment

    def get_is_available(self) -> bool:
        if not self.assignment.is_created: return False

        current_timestamp = self.session.scalar(func.current_timestamp())
        return current_timestamp >= self.assignment.available_date
    
    def get_is_closed(self) -> bool:
        if not self.assignment.is_created: return False

        current_timestamp = self.session.scalar(func.current_timestamp())
        return current_timestamp > self.assignment.due_date
    
    async def get_instructor_assignment_schema(self) -> InstructorAssignmentSchema:
        assignment = AssignmentSchema.from_orm(self.assignment).dict()
        assignment["is_available"] = self.get_is_available()
        assignment["is_closed"] = self.get_is_closed()

        return InstructorAssignmentSchema(**assignment)
    
class StudentAssignmentService(AssignmentService):
    def __init__(self, session: Session, student: StudentModel, assignment: AssignmentModel):
        super().__init__(session)
        self.student = student
        self.assignment = assignment
        self.extra_time_model = self._get_extra_time_model()

    def _get_extra_time_model(self) -> ExtraTimeModel | None:
        extra_time_model = self.session.query(ExtraTimeModel) \
            .filter(
                (ExtraTimeModel.assignment_id == self.assignment.id) &
                (ExtraTimeModel.student_id == self.student.id)
            ) \
            .first()
        return extra_time_model

    # The release date for a specific student, considering extra_time
    def get_adjusted_available_date(self) -> datetime | None:
        if self.assignment.available_date is None: return None

        deferred_time = self.extra_time_model.deferred_time if self.extra_time_model is not None else timedelta(0)
        
        return self.assignment.available_date + deferred_time

    # The due date for a specific student, considering extra_time
    def get_adjusted_due_date(self) -> datetime | None:
        if self.assignment.due_date is None: return None

        # If a student does not have any extra time allotted for the assignment,
        # allocate them a timedelta of 0.
        if self.extra_time_model is not None:
            deferred_time = self.extra_time_model.deferred_time
            extra_time = self.extra_time_model.extra_time
        else:
            deferred_time = timedelta(0)
            extra_time = timedelta(0)

        return self.assignment.due_date + deferred_time + extra_time + self.student.base_extra_time

    def get_is_available(self) -> bool:
        if not self.assignment.is_created: return False

        current_timestamp = self.session.scalar(func.current_timestamp())
        return current_timestamp >= self.get_adjusted_available_date()
    
    def get_is_closed(self) -> bool:
        if not self.assignment.is_created: return False

        current_timestamp = self.session.scalar(func.current_timestamp())
        return current_timestamp > self.get_adjusted_due_date()

    def validate_student_can_submit(self):
        if not self.assignment.is_created:
            raise AssignmentNotCreatedException()

        if not self.get_is_available():
            raise AssignmentNotOpenException()

        if self.get_is_closed():
            raise AssignmentClosedException()

    async def get_student_assignment_schema(self) -> StudentAssignmentSchema:
        assignment = AssignmentSchema.from_orm(self.assignment).dict()
        assignment["adjusted_available_date"] = self.get_adjusted_available_date()
        assignment["adjusted_due_date"] = self.get_adjusted_due_date()
        assignment["is_available"] = self.get_is_available()
        assignment["is_closed"] = self.get_is_closed()
        assignment["is_deferred"] = assignment["adjusted_available_date"] != assignment["available_date"]
        assignment["is_extended"] = assignment["adjusted_due_date"] != assignment["due_date"]

        return StudentAssignmentSchema(**assignment)