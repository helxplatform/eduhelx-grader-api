from .base import CustomException

class AssignmentNameTakenException(CustomException):
    code = 400
    error_code = "ASSIGNMENT__NAME_TAKEN"
    message = "assignment cannot use name that is already in use"

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

class AssignmentNotFoundException(CustomException):
    code = 404
    error_code = "ASSIGNMENT__NOT_FOUND"
    message = "assignment not found"
