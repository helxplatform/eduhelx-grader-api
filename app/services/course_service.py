from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.exc import SQLAlchemyError
from app.events import event_emitter
from app.models import CourseModel, StudentModel
from app.schemas import CourseWithInstructorsSchema, CourseSchema, UpdateCourseSchema, RepositoryConfigSchema
from app.events import CreateCourseCrudEvent, ModifyCourseCrudEvent, DeleteCourseCrudEvent
from app.core.exceptions import (
    MultipleCoursesExistException, NoCourseExistsException, CourseAlreadyExistsException,
    CourseEndsBeforeStartDateException, DatabaseTransactionException
)

class CourseService:
    def __init__(self, session: Session):
        self.session = session
    
    async def get_course(self) -> CourseModel:
        try:
            return self.session.query(CourseModel).one()
        except MultipleResultsFound as e:
            raise MultipleCoursesExistException()
        except NoResultFound as e:
            raise NoCourseExistsException()
    
    async def get_course_schema(self) -> CourseSchema:
        course = await self.get_course()
        return CourseSchema.from_orm(course)
    
    async def get_course_with_instructors_schema(self) -> CourseWithInstructorsSchema:
        from .user import InstructorService
        
        course = await self.get_course()
        course.instructors = await InstructorService(self.session).list_instructors()
        return CourseWithInstructorsSchema.from_orm(course)

    
    async def create_course(self, name: str, start_at: datetime = None, end_at: datetime = None) -> CourseModel:
        from app.services import GiteaService, CleanupService

        if start_at is not None and end_at is not None and start_at >= end_at:
            raise CourseEndsBeforeStartDateException()

        try:
            await self.get_course()
            raise CourseAlreadyExistsException()
        except NoCourseExistsException:
            pass

        with self.session.begin_nested():
            course = CourseModel(
                name=name,
                master_remote_url="",
                start_at=start_at,
                end_at=end_at
            )

            self.session.add(course)
            try:
                self.session.flush()
            except SQLAlchemyError as e:
                DatabaseTransactionException.from_exception(e)

            gitea_service = GiteaService(self.session)
            cleanup_service = CleanupService.Course(self.session, course)

            master_repository_name = self._compute_master_repository_name(name)
            instructor_organization_name = self._compute_instructor_gitea_organization_name(name)

            await gitea_service.create_organization(instructor_organization_name)
            
            try:
                master_remote_url = await gitea_service.create_repository(
                    name=master_repository_name,
                    description=f"The class master repository for { name }",
                    owner=instructor_organization_name,
                    private=True
                )
                await gitea_service.set_git_hook(
                    repository_name=master_repository_name,
                    owner=instructor_organization_name,
                    hook_id="pre-receive",
                    hook_content=await gitea_service.get_merge_control_hook()
                )
                course.master_remote_url = master_remote_url
                await event_emitter.emit_async(CreateCourseCrudEvent(course=course))
            except Exception as e:
                await cleanup_service.undo_create_course(delete_gitea_organization=True)
                raise e
            
        self.session.commit()
        return course
    
    async def update_course(self, update_course: UpdateCourseSchema) -> CourseModel:
        course = await self.get_course()
        update_fields = update_course.dict(exclude_unset=True)

        with self.session.begin_nested():
            if "name" in update_fields:
                course.name = update_fields["name"]
            
            if "start_at" in update_fields:
                course.start_at = update_fields["start_at"]

            if "end_at" in update_fields:
                course.end_at = update_fields["end_at"]
            
            if "master_remote_url" in update_fields:
                course.master_remote_url = update_fields["master_remote_url"]

            if course.start_at is not None and course.end_at is not None and course.start_at >= course.end_at:
                raise CourseEndsBeforeStartDateException()

            try:
                self.session.flush()
            except SQLAlchemyError as e:
                DatabaseTransactionException.raise_exception(e)

            await event_emitter.emit_async(ModifyCourseCrudEvent(course=course, modified_fields=list(update_fields.keys())))

        self.session.commit()
        return course

    async def get_instructor_gitea_organization_name(self) -> str:
        course = await self.get_course()
        return self._compute_instructor_gitea_organization_name(course.name)
    
    async def get_master_repository_name(self) -> str:
        course = await self.get_course()
        # No spaces allowed! (learned the hard way...)
        return self._compute_master_repository_name(course.name)
        
    async def get_student_repository_name(self, student_onyen: str) -> str:
        course = await self.get_course()
        return self._compute_student_repository_name(course.name)
    
    async def get_master_branch_name(self) -> str:
        return self._compute_master_branch_name()
    
    """ So that other services don't have to call 3 methods every time they want to access the master repo. """
    async def get_master_repository_config(self) -> RepositoryConfigSchema:
        course = await self.get_course()
        return RepositoryConfigSchema(
            name=self._compute_master_repository_name(course.name),
            owner=self._compute_instructor_gitea_organization_name(course.name),
            master_branch=self._compute_master_branch_name(),
            remote_url=course.master_remote_url
        )
    
    async def get_student_repository_config(self, student: StudentModel) -> RepositoryConfigSchema:
        course = await self.get_course()
        return RepositoryConfigSchema(
            name=self._compute_student_repository_name(course.name),
            owner=student.onyen,
            master_branch=self._compute_master_branch_name(),
            remote_url=student.fork_remote_url
        )


    @staticmethod
    def _compute_instructor_gitea_organization_name(course_name: str) -> str:
        return f"{ course_name.replace(' ', '_') }-instructors"
    
    @staticmethod
    def _compute_master_repository_name(course_name: str) -> str:
        return f"{ course_name.replace(' ', '_') }-class-master-repo"
    
    @classmethod
    def _compute_student_repository_name(cls, course_name: str) -> str:
        return f"{ course_name.replace(' ', '_') }-student-repo"
    
    @classmethod
    def _compute_master_branch_name(cls) -> str:
        return "main"