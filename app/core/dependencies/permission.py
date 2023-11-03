from abc import ABC, abstractmethod
from typing import List, Type

from fastapi import Request
from fastapi.openapi.models import APIKey, APIKeyIn
from fastapi.security.base import SecurityBase

from app.services import UserService
from app.core.config import settings
from app.database import SessionLocal
from app.models import StudentModel, InstructorModel
from app.core.role_permissions import UserPermission
from app.core.exceptions import (
    UnauthorizedException, MissingPermissionException, UserNotFoundException,
    NotAStudentException, NotAnInstructorException, NotASuperuserException
)

class BasePermission(ABC):
    def __init__(self, db, user):
        self.db = db
        self.user = user

    @abstractmethod
    async def verify_permission(self, request: Request):
        pass

# For endpoints that require a user to be logged in, but nothing beyond that.
class RequireLoginPermission(BasePermission):
    async def verify_permission(self, request: Request):
        if self.user is None or self.user.role is None:
            raise UnauthorizedException()

class UserIsStudentPermission(RequireLoginPermission):
    async def verify_permission(self, request: Request):
        await super().verify_permission(request)
        
        if not isinstance(self.user, StudentModel):
            raise NotAStudentException()

class UserIsInstructorPermission(RequireLoginPermission):
    async def verify_permission(self, request: Request):
        await super().verify_permission(request)

        if not isinstance(self.user, InstructorModel):
            raise NotAnInstructorException()
        
# We'll define a superuser here as anything other than a student.
# This definition is useful in endpoints where we want to allow
# access to everyone other than students without restricting access
# to just instructors. 
class UserIsSuperuserPermission(RequireLoginPermission):
    async def verify_permission(self, request: Request):
        await super().verify_permission(request)

        if isinstance(self.user, StudentModel):
            raise NotASuperuserException()
        

class BaseRolePermission(RequireLoginPermission):
    permission: UserPermission

    async def verify_permission(self, request: Request):
        await super().verify_permission(request)

        for permission in self.user.role.permissions:
            if permission == self.permission:
                return
                
        raise MissingPermissionException(self.permission)


class AssignmentListPermission(BaseRolePermission):
    permission: UserPermission.ASSIGNMENT__GET
class AssignmentCreatePermission(BaseRolePermission):
    permission = UserPermission.ASSIGNMENT__CREATE
class AssignmentModifyPermission(BaseRolePermission):
    permission = UserPermission.ASSIGNMENT__MODIFY
class AssignmentDeletePermission(BaseRolePermission):
    permission = UserPermission.ASSIGNMENT__DELETE

class CourseListPermission(BaseRolePermission):
    permission = UserPermission.COURSE__GET
class CourseCreatePermission(BaseRolePermission):
    permission = UserPermission.COURSE__CREATE
class CourseModifyPermission(BaseRolePermission):
    permission = UserPermission.COURSE__MODIFY
class CourseDeletePermission(BaseRolePermission):
    permission = UserPermission.COURSE__DELETE

class StudentListPermission(BaseRolePermission):
    permission = UserPermission.STUDENT__GET
class StudentCreatePermission(BaseRolePermission):
    permission = UserPermission.STUDENT__CREATE
class StudentModifyPermission(BaseRolePermission):
    permission = UserPermission.STUDENT__MODIFY
class StudentDeletePermission(BaseRolePermission):
    permission = UserPermission.STUDENT__DELETE

class InstructorListPermission(BaseRolePermission):
    permission = UserPermission.INSTRUCTOR__GET
class InstructorCreatePermission(BaseRolePermission):
    permission = UserPermission.INSTRUCTOR__CREATE
class InstructorModifyPermission(BaseRolePermission):
    permission = UserPermission.INSTRUCTOR__MODIFY
class InstructorDeletePermission(BaseRolePermission):
    permission = UserPermission.INSTRUCTOR__DELETE

class SubmissionListPermission(BaseRolePermission):
    permission = UserPermission.SUBMISSION__GET
class SubmissionCreatePermission(BaseRolePermission):
    permission = UserPermission.SUBMISSION__CREATE
class SubmissionModifyPermission(BaseRolePermission):
    permission = UserPermission.SUBMISSION__MODIFY
class SubmissionDeletePermission(BaseRolePermission):
    permission = UserPermission.SUBMISSION__DELETE


class PermissionDependency(SecurityBase):
    def __init__(self, *permissions: List[Type[BasePermission]]):
        self.permissions = permissions
        self.model: APIKey = APIKey(**{"in": APIKeyIn.header}, name="Authorization")
        self.scheme_name = self.__class__.__name__

    async def __call__(self, request: Request):
        if settings.DISABLE_AUTHENTICATION:
            # If authentication is disabled, we treat the anonymous user as if they have every permission.
            return

        with SessionLocal() as session:
            try:
                user = await UserService(session).get_user_by_onyen(request.user.onyen)
            except UserNotFoundException:
                user = None
            
            for permission in self.permissions:
                cls = permission(session, user)
                await cls.verify_permission(request=request)