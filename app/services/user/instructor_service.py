from typing import List
from app.models import InstructorModel
from app.core.utils.auth_helper import PasswordHelper
from app.core.exceptions import PasswordDoesNotMatchException, NotAnInstructorException
from .user_service import UserService

class InstructorService(UserService):
    async def list_instructors(self) -> List[InstructorModel]:
        return self.session.query(InstructorModel).all()

    async def create_instructor(
        self,
        onyen: str,
        first_name: str,
        last_name: str,
        email: str,
        password: str,
        confirm_password: str
    ):
        if password != confirm_password:
            raise PasswordDoesNotMatchException()
        instructor = InstructorModel(
            onyen=onyen,
            first_name=first_name,
            last_name=last_name,
            email=email,
            password=PasswordHelper.hash_password(password),
            role_name="instructor"
        )
        self.session.add(instructor)
        self.session.commit()

    async def get_user_by_onyen(self, onyen: str) -> InstructorModel:
        user = await super().get_user_by_onyen(onyen)
        if not isinstance(user, InstructorModel):
            raise NotAnInstructorException()
        return user