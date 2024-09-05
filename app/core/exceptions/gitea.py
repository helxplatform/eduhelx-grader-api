from __future__ import annotations
from httpx import Request, Response, HTTPStatusError
from .base import CustomException

class GiteaBackendException(CustomException):
    code = 500
    error_code = "GITEA__SERVICE_EXCEPTION"
    message = "An error occurred while interacting with Gitea"
    response: Response | None = None

    def __init__(self, message: str | None = None, request: Request | None = None, response: Response | None = None):
        super().__init__(message)
        self.request = request
        self.response = response

    @property
    def status_code(self) -> int | None:
        if self.response: return self.response.status_code
        return None
    
    @classmethod
    def from_exception(cls, exc: HTTPStatusError) -> GiteaBackendException:
        if exc.response.status_code == 401:
            cls = GiteaUnauthorizedException
        elif exc.response.status_code == 403:
            cls = GiteaForbiddenException
        elif exc.response.status_code == 404:
            cls = GiteaNotFoundException
            
        return cls(exc.response.text, exc.request, exc.response)

class GiteaUnauthorizedException(GiteaBackendException):
    code = 401
    error_code = "GITEA__NOT_AUTHORIZED"
    message = "gitea backend encountered a 401"

class GiteaForbiddenException(GiteaBackendException):
    code = 403
    error_code = "GITEA__FORBIDDEN"
    message = "gitea backend encountered a 403"

class GiteaNotFoundException(GiteaBackendException):
    code = 404
    error_code = "GITEA__NOT_FOUND"
    message = "gitea backend encountered a 404"