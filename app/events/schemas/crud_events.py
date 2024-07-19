from enum import Enum
from app.events.emitter import PydanticEvent
from app.models import CourseModel, AssignmentModel, SubmissionModel, UserModel, StudentModel, InstructorModel
from app.models.user import UserType

class CrudType(str, Enum):
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"

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
    modified_fields: list[str] | None = None

    @property
    def crud_type(self):
        return self.__event_name__.split(":")[2]

    @property
    def resource_type(self):
        return self.__event_name__.split(":")[1]

class CourseCrudEvent(CrudEvent):
    course: CourseModel

class CreateCourseCrudEvent(CourseCrudEvent):
    __event_name__ = CrudEvents.CREATE_COURSE.value
class ModifyCourseCrudEvent(CourseCrudEvent):
    __event_name__ = CrudEvents.MODIFY_COURSE.value
class DeleteCourseCrudEvent(CourseCrudEvent):
    __event_name__ = CrudEvents.DELETE_COURSE.value


class UserCrudEvent(CrudEvent):
    user: UserModel

    @property
    def user_type(self):
        if isinstance(self.user, StudentModel):
            return UserType.STUDENT
        
        if isinstance(self.user, InstructorModel):
            return UserType.INSTRUCTOR

        raise NotImplementedError

class CreateUserCrudEvent(UserCrudEvent):
    __event_name__ = CrudEvents.CREATE_USER.value
class ModifyUserCrudEvent(UserCrudEvent):
    __event_name__ = CrudEvents.MODIFY_USER.value
class DeleteUserCrudEvent(UserCrudEvent):
    __event_name__ = CrudEvents.DELETE_USER.value


class AssignmentCrudEvent(CrudEvent):
    assignment: AssignmentModel

class CreateAssignmentCrudEvent(AssignmentCrudEvent):
    __event_name__ = CrudEvents.CREATE_ASSIGNMENT.value
class ModifyAssignmentCrudEvent(AssignmentCrudEvent):
    __event_name__ = CrudEvents.MODIFY_ASSIGNMENT.value
class DeleteAssignmentCrudEvent(AssignmentCrudEvent):
    __event_name__ = CrudEvents.DELETE_ASSIGNMENT.value


class SubmissionCrudEvent(CrudEvent):
    submission: SubmissionModel

class CreateSubmissionCrudEvent(SubmissionCrudEvent):
    __event_name__ = CrudEvents.CREATE_SUBMISSION.value
class ModifySubmissionCrudEvent(SubmissionCrudEvent):
    __event_name__ = CrudEvents.MODIFY_SUBMISSION.value
class DeleteSubmissionCrudEvent(SubmissionCrudEvent):
    __event_name__ = CrudEvents.DELETE_SUBMISSION.value