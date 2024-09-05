from .base import CustomException

class UserAlreadyExistsException(CustomException):
    code = 409
    error_code = "USER__ONYEN_OR_EMAIL_ALREADY_EXISTS"
    message = "onyen or email is already in use by another user"

class PasswordDoesNotMatchException(CustomException):
    code = 401
    error_code = "USER__PASSWORD_DOES_NOT_MATCH"
    message = "password does not match"

class DuplicateEmailOrOnyen(CustomException):
    code = 409
    error_code = "USER__DUPLICATE_EMAIL_OR_NICKNAME"
    message = "duplicate email or onyen"

class UserNotFoundException(CustomException):
    code = 404
    error_code = "USER__NOT_FOUND"
    message = "user not found"

class NotAStudentException(CustomException):
    code = 403
    error_code = "USER__NOT_A_STUDENT"
    message = "user is not a student"

class NotAnInstructorException(CustomException):
    code = 403
    error_code = "USER__NOT_AN_INSTRUCTOR"
    message = "user is not an instructor"

class NotASuperuserException(CustomException):
    code = 403
    error_code = "USER__NOT_A_SUPERUSER"
    message = "user is not a superuser"
