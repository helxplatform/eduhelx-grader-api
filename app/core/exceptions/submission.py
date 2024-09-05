from .base import CustomException

class SubmissionNotFoundException(CustomException):
    code = 404
    error_code = "SUBMISSION__NOT_FOUND"
    message = "submission not found"

class SubmissionMaxAttemptsReachedException(CustomException):
    code = 409
    error_code = "SUBMISSION__MAX_ATTEMPTS_REACHED"
    message = "you have reached the maximum number of submissions allowed for this assignment"