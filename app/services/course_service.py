from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from app.events import dispatch
from app.models import CourseModel
from app.schemas import CourseWithInstructorsSchema, CourseSchema, UpdateCourseSchema, FileOperation, FileOperationType
from app.events import CreateCourseCrudEvent, ModifyCourseCrudEvent, DeleteCourseCrudEvent
from app.core.exceptions import MultipleCoursesExistException, NoCourseExistsException, CourseAlreadyExistsException

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

        try:
            await self.get_course()
            raise CourseAlreadyExistsException()
        except NoCourseExistsException:
            pass
        
        print("CREATING COURSE")

        master_remote_url = ""

        course = CourseModel(
            name=name,
            master_remote_url="",
            start_at=start_at,
            end_at=end_at
        )

        self.session.add(course)
        self.session.commit()

        gitea_service = GiteaService(self.session)
        cleanup_service = CleanupService.Course(self.session, course)

        master_repository_name = self._compute_master_repository_name(name)
        instructor_organization_name = self._compute_instructor_gitea_organization_name(name)
        master_branch_name = self._compute_master_branch_name()
        file_operations = [
            FileOperation(content=".ssh\n", path=".gitignore", operation=FileOperationType.CREATE)
        ]

        try:
            await gitea_service.create_organization(instructor_organization_name)
            print("CREATED GITEA ORGANIZATION")
        except Exception as e:
            await cleanup_service.undo_create_course(delete_database_course=True)
            print("UNDO COURSE CREATE (db=True)")
            raise e
        
        try:
            master_remote_url = await gitea_service.create_repository(
                name=master_repository_name,
                description=f"The class master repository for { name }",
                owner=instructor_organization_name,
                private=True
            )
            print("CREATED CLASS MASTER REPOSITORY")
            await gitea_service.modify_repository_files(
                name=master_repository_name,
                owner=instructor_organization_name,
                branch_name=master_branch_name,
                commit_message="Initial commit",
                files=file_operations
            )
            await gitea_service.set_git_hook(
                repository_name=master_repository_name,
                owner=instructor_organization_name,
                hook_id="pre-receive",
                hook_content=await gitea_service.get_master_repo_prereceive_hook()
            )
            print("SET CLASS MASTER REPO HOOK")
            course.master_remote_url = master_remote_url
            self.session.commit()
            
        except Exception as e:
            await cleanup_service.undo_create_course(delete_database_course=True, delete_gitea_organization=True)
            print("UNDO CREATE COURSE (db=True, gitea_org=True)")
            raise e
        
        course.master_remote_url = master_remote_url
        self.session.commit()

        dispatch(CreateCourseCrudEvent(course=course))
        print("DONE CREATING COURSE")
        return course
    
    async def update_course(self, update_course: UpdateCourseSchema) -> CourseModel:
        course = await self.get_course()
        update_fields = update_course.dict(exclude_unset=True)

        if "name" in update_fields:
            course.name = update_fields["name"]
        
        if "start_at" in update_fields:
            course.start_at = update_fields["start_at"]

        if "end_at" in update_fields:
            course.end_at = update_fields["end_at"]
        
        if "master_remote_url" in update_fields:
            course.master_remote_url = update_fields["master_remote_url"]

        self.session.commit()

        dispatch(ModifyCourseCrudEvent(course=course, modified_fields=list(update_fields.keys())))

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

    @staticmethod
    def _compute_instructor_gitea_organization_name(course_name: str) -> str:
        course_name_string = course_name.replace(' ', '_')
        parts = course_name_string.split('_', 3)
        short_name = '_'.join(parts[:3])
        return f"{ short_name }-instructors"
    
    @staticmethod
    def _compute_master_repository_name(course_name: str) -> str:
        return f"{ course_name.replace(' ', '_') }-class-master-repo"
    
    @classmethod
    def _compute_student_repository_name(cls, course_name: str) -> str:
        return f"{ course_name.replace(' ', '_') }-student-repo"
    
    @classmethod
    def _compute_master_branch_name(cls) -> str:
        return "main"