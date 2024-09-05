import asyncio
from app.events import dispatch, CreateUserCrudEvent
from app.models import InstructorModel
from app.schemas import CreateInstructorSchema
from app.core.role_permissions import instructor_role
from app.core.exceptions import NotAnInstructorException, UserAlreadyExistsException, UserNotFoundException
from .user_service import UserService, UserCleanupMetadata

class InstructorService(UserService):
    async def list_instructors(self) -> list[InstructorModel]:
        return self.session.query(InstructorModel).all()
    
    async def create_instructors(
        self,
        instructors: list[CreateInstructorSchema]
    ) -> list[InstructorModel]:
        from app.services import GiteaService, CourseService, CleanupService
        
        """ This makes batch cleanup much more clean since aborts can occur partway through non-batch operations """
        cleanup_metadata: dict[str, UserCleanupMetadata] = {
            instructor.onyen: UserCleanupMetadata(database_user_hit=True)
            for instructor in instructors
        }
        async def cleanup():
            for onyen, metadata in cleanup_metadata.items():
                instructor = [u for u in instructor_models if u.onyen == onyen][0]
                await CleanupService.User(self.session, instructor).undo_create_user(
                    delete_database_user=metadata.database_user_hit,
                    delete_password_secret=metadata.password_secret_hit,
                    delete_gitea_user=metadata.gitea_user_hit
                )

        """ Create autogen passwords """
        async def create_user_password(instructor: InstructorModel) -> str:
            autogen_password = await self.create_user_auto_password_auth(instructor.onyen)
            cleanup_metadata[instructor.onyen].password_secret_hit = True

            return autogen_password

        """ Create Gitea instructors """
        async def create_gitea_instructor(instructor: InstructorModel, autogen_password: str) -> None:
            await gitea_service.create_user(instructor.onyen, instructor.email, autogen_password)
            cleanup_metadata[instructor.onyen].gitea_user_hit = True
                
            await gitea_service.add_user_to_organization(instructor_org_name, instructor.onyen)

        gitea_service = GiteaService(self.session)
        course_service = CourseService(self.session)

        instructor_org_name = await course_service.get_instructor_gitea_organization_name()

        """ Create models """
        instructor_models = []
        for instructor in instructors:
            try:
                await super().get_user_by_onyen(instructor.onyen)
                raise UserAlreadyExistsException()
            except UserNotFoundException:
                pass
            
            try:
                await super().get_user_by_email(instructor.email)
                raise UserAlreadyExistsException()
            except UserNotFoundException:
                pass

            instructor_models.append(InstructorModel(
                onyen=instructor.onyen,
                name=instructor.name,
                email=instructor.email,
                role=instructor_role
            ))
            
        self.session.add_all(instructor_models)
        self.session.commit()
        for metadata in cleanup_metadata.values(): metadata.database_user_hit = True

        """ Create passwords """
        autogen_passwords = []
        try:
            autogen_passwords += await asyncio.gather(*[
                create_user_password(instructor)
                for instructor in instructor_models
            ])
        except Exception as e:
            await cleanup()
            raise e
        
        """ Create Gitea users """
        try:
            await asyncio.gather(*[
                create_gitea_instructor(instructor, autogen_password)
                for instructor, autogen_password in zip(instructor_models, autogen_passwords)
            ])
        except Exception as e:
            await cleanup()
            raise e

        for instructor in instructor_models:
            dispatch(CreateUserCrudEvent(user=instructor))

        return instructor_models
    
    async def create_instructor(self, instructor: CreateInstructorSchema) -> InstructorModel:
        instructors = await self.create_instructors([instructor])
        return instructors[0]

    async def get_user_by_onyen(self, onyen: str) -> InstructorModel:
        user = await super().get_user_by_onyen(onyen)
        if not isinstance(user, InstructorModel):
            raise NotAnInstructorException()
        return user