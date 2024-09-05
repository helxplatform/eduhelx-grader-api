import asyncio
from app.events import dispatch
from app.models import StudentModel
from app.events import CreateUserCrudEvent
from app.schemas import CollaboratorPermission, CreateStudentSchema
from app.core.role_permissions import student_role
from app.core.exceptions import NotAStudentException, UserAlreadyExistsException, UserNotFoundException
from .user_service import UserService, UserCleanupMetadata

class StudentService(UserService):
    async def list_students(
        self,
    ) -> list[StudentModel]:
        return self.session.query(StudentModel).all()
    
    async def create_students(
        self,
        students: list[CreateStudentSchema]
    ) -> list[StudentModel]:
        from app.services import GiteaService, CourseService, CleanupService

        """ This makes batch cleanup much more clean since aborts can occur partway through non-batch operations """
        cleanup_metadata: dict[str, UserCleanupMetadata] = {
            student.onyen: UserCleanupMetadata(database_user_hit=True)
            for student in students
        }
        async def cleanup():
            for onyen, metadata in cleanup_metadata.items():
                student = [u for u in student_models if u.onyen == onyen][0]
                await CleanupService.User(self.session, student).undo_create_user(
                    delete_database_user=metadata.database_user_hit,
                    delete_password_secret=metadata.password_secret_hit,
                    delete_gitea_user=metadata.gitea_user_hit
                )


        """ Create autogen passwords """
        async def create_user_password(student: StudentModel) -> str:
            autogen_password = await self.create_user_auto_password_auth(student.onyen)
            cleanup_metadata[student.onyen].password_secret_hit = True

            return autogen_password

        """ Create Gitea students. """
        async def create_gitea_student(student: StudentModel, autogen_password: str) -> None:
            await gitea_service.create_user(student.onyen, student.email, autogen_password)
            cleanup_metadata[student.onyen].gitea_user_hit = True

            await gitea_service.add_collaborator_to_repo(
                name=master_repo_name,
                owner=instructor_organization,
                collaborator_name=student.onyen,
                permission=CollaboratorPermission.READ
            )
        
        """ Create Gitea student forks. This modifies the database but does not commit. """
        """ NOTE: User forks currently cannot be created concurrently due to a restriction of Gitea/Gitea-Assist.
        Gitea only allows forking under the authenticated user, and does not allow renaming during creation, so
        concurrent fork creation can result in two forks being created under the same name under the Gitea-Assist account. """
        async def create_student_fork(student: StudentModel) -> None:
            await gitea_service.fork_repository(
                name=master_repo_name,
                owner=instructor_organization,
                new_owner=student.onyen
            )
            # The remote is subject to change when the repo is renamed, so
            # we don't want to use the remote returned by fork_repository.
            student.fork_remote_url = await gitea_service.modify_repository(
                name=master_repo_name,
                owner=student.onyen,
                new_name=await course_service.get_student_repository_name(student.onyen)
            )

        gitea_service = GiteaService(self.session)
        course_service = CourseService(self.session)

        master_repo_name = await course_service.get_master_repository_name()
        instructor_organization = await course_service.get_instructor_gitea_organization_name()

        """ Create models """
        student_models = []
        for student in students:
            try:
                await super().get_user_by_onyen(student.onyen)
                raise UserAlreadyExistsException()
            except UserNotFoundException:
                pass
            
            try:
                await super().get_user_by_email(student.email)
                raise UserAlreadyExistsException()
            except UserNotFoundException:
                pass

            student_models.append(StudentModel(
                onyen=student.onyen,
                name=student.name,
                email=student.email,
                role=student_role
            ))
        
        self.session.add_all(student_models)
        self.session.commit()
        for metadata in cleanup_metadata.values(): metadata.database_user_hit = True

        """ Create passwords """
        autogen_passwords = []
        try:
            autogen_passwords += await asyncio.gather(*[
                create_user_password(student)
                for student in student_models
            ])
        except Exception as e:
            await cleanup()
            raise e

        """ Create Gitea users """
        try:
            await asyncio.gather(*[
                create_gitea_student(student, autogen_password)
                for student, autogen_password in zip(student_models, autogen_passwords)
            ])
            for student in student_models:
                await create_student_fork(student)

            # We've updated the `fork_remote_url` column for students
            self.session.commit()
        except Exception as e:
            await cleanup()
            raise e

        for student in student_models:
            dispatch(CreateUserCrudEvent(user=student))
        
        return student_models
    
    async def create_student(self, student: CreateStudentSchema) -> StudentModel:
        students = await self.create_students([student])
        return students[0]

    async def get_user_by_onyen(self, onyen: str) -> StudentModel:
        user = await super().get_user_by_onyen(onyen)
        if not isinstance(user, StudentModel):
            raise NotAStudentException()
        return user
    
    async def set_fork_cloned(self, student: StudentModel) -> None:
        student.fork_cloned = True
        self.session.commit()

    async def get_total_students(self) -> int:
        return self.session.query(StudentModel).count()
