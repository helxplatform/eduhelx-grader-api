from .base import CustomException

class AssignmentDueBeforeOpenException(CustomException):
    code = 400
    error_code = "ASSIGNMENT__DUE_BEFORE_OPEN"
    message = "assignment cannot be due before it has opened"

class AssignmentNotOpenException(CustomException):
    code = 403
    error_code = "ASSIGNMENT__NOT_OPEN"
    message = "assignment not open to student yet"

class AssignmentClosedException(CustomException):
    code = 403
    error_code = "ASSIGNMENT__CLOSED"
    message = "assignment closed for student"

class AssignmentNotCreatedException(CustomException):
    code = 403
    error_code = "ASSIGNMENT__NOT_CREATED"
    message = "assignment not created"

class AssignmentNotPublishedException(CustomException):
    code = 403
    error_code = "ASSIGNMENT__NOT_PUBLISHED"
    message = "assignment not published"

class AssignmentNotFoundException(CustomException):
    code = 404
    error_code = "ASSIGNMENT__NOT_FOUND"
    message = "assignment not found"
