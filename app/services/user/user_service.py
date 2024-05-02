from sqlalchemy.orm import Session
from app.models import UserModel, AutoPasswordAuthModel
from app.schemas import RefreshTokenSchema
from app.core.config import settings
from app.core.utils.token_helper import TokenHelper
from app.core.utils.auth_helper import PasswordHelper
from app.core.middleware.authentication import CurrentUser
from app.core.exceptions import (
    PasswordDoesNotMatchException,
    UserNotFoundException,
    PasswordDoesNotMatchException
)

class UserService:
    def __init__(self, session: Session):
        self.session = session

    async def get_user_by_id(self, id: int) -> UserModel:
        user = self.session.query(UserModel).filter_by(id=id).first()
        if user is None:
            raise UserNotFoundException()
        return user

    async def get_user_by_onyen(self, onyen: str) -> UserModel:
        user = self.session.query(UserModel).filter_by(onyen=onyen).first()
        if user is None:
            raise UserNotFoundException()
        return user

    async def get_user_by_email(self, email: str) -> UserModel:
        user = self.session.query(UserModel).filter_by(email=email).first()
        if user is None:
            raise UserNotFoundException()
        return user

    async def login(self, onyen: str, autogen_password: str) -> RefreshTokenSchema:
        user = self.session.query(UserModel).filter_by(onyen=onyen).first()
        user_auth = self.session.query(AutoPasswordAuthModel).filter_by(onyen=onyen).first()
        if not user or not user_auth:
            raise UserNotFoundException()
        if not PasswordHelper.verify_password(autogen_password, user_auth.autogen_password_hash):
            raise PasswordDoesNotMatchException()

        current_user = CurrentUser(id=user.id, onyen=user.onyen)

        response = RefreshTokenSchema(
            access_token=TokenHelper.encode(payload=current_user.dict(), expire_period=settings.ACCESS_TOKEN_EXPIRES_MINUTES),
            refresh_token=TokenHelper.encode(payload={"sub": "refresh", **current_user.dict()}, expire_period=settings.REFRESH_TOKEN_EXPIRES_MINUTES)
        )
        return response
    
    async def create_user_auto_password_auth(self, onyen: str) -> str:
        from app.services import CourseService, KubernetesService
        
        autogen_password = PasswordHelper.generate_password(64)
        autogen_password_hash = PasswordHelper.hash_password(autogen_password)

        user_auth = AutoPasswordAuthModel(
            onyen=onyen,
            autogen_password_hash=autogen_password_hash
        )
        self.session.add(user_auth)
        self.session.commit()

        course = await CourseService(self.session).get_course()
        user = await self.get_user_by_onyen(onyen)
        KubernetesService().create_credential_secret(
            course_name=course.name,
            onyen=onyen,
            password=autogen_password,
            user_type=user.user_type
        )

        return autogen_password
    
    async def delete_user_auto_password_auth(self, onyen: str) -> str:
        from app.services import CourseService, KubernetesService, GiteaService

        course = await CourseService(self.session).get_course()
        user_auth = self.session.query(AutoPasswordAuthModel).filter_by(onyen=onyen).first()

        KubernetesService().delete_credential_secret(course.name, onyen)

        self.session.delete(user_auth)
        self.session.commit()

    async def delete_user(
        self,
        onyen: str
    ) -> None:
        from app.services import GiteaService, KubernetesService, CourseService
        
        await self.delete_user_auto_password_auth(onyen)
        
        user = await self.get_user_by_onyen(onyen)
        self.session.delete(user)
        self.session.commit()

        gitea_service = GiteaService()
        await gitea_service.delete_user(onyen, purge=True)