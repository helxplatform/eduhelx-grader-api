from enum import Enum
from app.events.emitter import PydanticEvent
from app.models import CourseModel, AssignmentModel, SubmissionModel, UserModel, StudentModel, InstructorModel
from app.models.user import UserType

class CrudType(str, Enum):
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"

class ResourceType(str, Enum):
    COURSE = "COURSE"
    USER = "USER"
    ASSIGNMENT = "ASSIGNMENT"
    SUBMISSION = "SUBMISSION"

class CrudEvents(Enum):
    CREATE_COURSE = "crud:course:create"
    MODIFY_COURSE = "crud:course:modify"
    DELETE_COURSE = "crud:course:delete"

    CREATE_USER = "crud:user:create"
    MODIFY_USER = "crud:user:modify"
    DELETE_USER = "crud:user:delete"

    CREATE_ASSIGNMENT = "crud:assignment:create"
    MODIFY_ASSIGNMENT = "crud:assignment:modify"
    DELETE_ASSIGNMENT = "crud:assignment:delete"

    CREATE_SUBMISSION = "crud:submission:create"
    MODIFY_SUBMISSION = "crud:submission:modify"
    DELETE_SUBMISSION = "crud:submission:delete"

class CrudEvent(PydanticEvent):
    crud_type: CrudType
    resource_type: ResourceType

class CourseCrudEvent(CrudEvent):
    course: CourseModel
    resource_type = ResourceType.COURSE

class CreateCourseCrudEvent(CourseCrudEvent):
    __event_name__ = CrudEvents.CREATE_COURSE.value
    crud_type = CrudType.CREATE
class ModifyCourseCrudEvent(CourseCrudEvent):
    __event_name__ = CrudEvents.MODIFY_COURSE.value
    crud_type = CrudType.MODIFY
class DeleteCourseCrudEvent(CourseCrudEvent):
    __event_name__ = CrudEvents.DELETE_COURSE.value
    crud_type = CrudType.DELETE


class UserCrudEvent(CrudEvent):
    user: UserModel
    resource_type = ResourceType.USER

    @property
    def user_type(self):
        if isinstance(self.user, StudentModel):
            return UserType.STUDENT
        
        if isinstance(self.user, InstructorModel):
            return UserType.INSTRUCTOR

        raise NotImplementedError

class CreateUserCrudEvent(UserCrudEvent):
    __event_name__ = CrudEvents.CREATE_USER.value
    crud_type = CrudType.CREATE
class ModifyUserCrudEvent(UserCrudEvent):
    __event_name__ = CrudEvents.MODIFY_USER.value
    crud_type = CrudType.MODIFY
class DeleteUserCrudEvent(UserCrudEvent):
    __event_name__ = CrudEvents.DELETE_USER.value
    crud_type = CrudType.DELETE


class AssignmentCrudEvent(CrudEvent):
    assignment: AssignmentModel
    resource_type = ResourceType.ASSIGNMENT

class CreateAssignmentCrudEvent(AssignmentCrudEvent):
    __event_name__ = CrudEvents.CREATE_ASSIGNMENT.value
    crud_type = CrudType.CREATE
class ModifyAssignmentCrudEvent(AssignmentCrudEvent):
    __event_name__ = CrudEvents.MODIFY_ASSIGNMENT.value
    crud_type = CrudType.MODIFY
class DeleteAssignmentCrudEvent(AssignmentCrudEvent):
    __event_name__ = CrudEvents.DELETE_ASSIGNMENT.value
    crud_type = CrudType.DELETE


class SubmissionCrudEvent(CrudEvent):
    submission: SubmissionModel
    resource_type = ResourceType.SUBMISSION

class CreateSubmissionCrudEvent(SubmissionCrudEvent):
    __event_name__ = CrudEvents.CREATE_SUBMISSION.value
    crud_type = CrudType.CREATE
class ModifySubmissionCrudEvent(SubmissionCrudEvent):
    __event_name__ = CrudEvents.MODIFY_SUBMISSION.value
    crud_type = CrudType.MODIFY
class DeleteSubmissionCrudEvent(SubmissionCrudEvent):
    __event_name__ = CrudEvents.DELETE_SUBMISSION.value
    crud_type = CrudType.DELETE