from httpx import Response
from .base import CustomException

class LMSUserNotFoundException(CustomException):
    code = 404
    error_code = "LMS__USER_NOT_FOUND"
    message = "User's onyen is not associated with an LMS user"

class LMSFileNotFoundException(CustomException):
    code = 404
    error_code = "LMS__FILE_NOT_FOUND"
    message = "File does not exist in LMS file storage"

class LMSFolderNotFoundException(CustomException):
    code = 404
    error_code = "LMS__FOLDER_NOT_FOUND"
    message = "Folder does not exist in LMS file storage"

class LMSFileUploadException(CustomException):
    code = 500
    error_code = "LMS__FILE_UPLOAD_FAILED"
    message = "The file failed to upload to the LMS"

class LMSUserPIDAlreadyAssociatedException(CustomException):
    code = 409
    error_code = "LMS__USER_PID_ALREADY_ASSOCIATED"
    message = "LMS PID is already associated with a different Eduhelx user's onyen"

class LMSBackendException(CustomException):
    code = 500
    error_code = "LMS__SERVICE_EXCEPTION"
    message = "An error occurred while interacting with the LMS"
    response: Response | None = None

    def __init__(self, message: str | None = None, response: Response | None = None):
        super().__init__(message)
        self.response = response

    @property
    def status_code(self) -> int | None:
        if self.response: return self.response.status_code
        return None