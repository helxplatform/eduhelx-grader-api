from .base import CustomException

class SubmissionNotFoundException(CustomException):
    code = 404
    error_code = "SUBMISSION__NOT_FOUND"
    message = "submission not found"

class SubmissionCommitNotFoundException(CustomException):
    code = 404
    error_code = "SUBMISSION__COMMIT_HASH_NOT_FOUND"
    message = "commit sha could not found inside repostiory"