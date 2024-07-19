import requests
import httpx
from pydantic import BaseModel
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.models import UserModel, OnyenPIDModel
from app.services import UserService, UserType
from app.core.exceptions import (
    LMSNoCourseFetchedException, LMSNoAssignmentFetchedException, LMSNoStudentsFetchedException,
    LMSUserNotFoundException, LMSUserPIDAlreadyAssociatedException, LMSBackendException,
    DatabaseTransactionException
)

class UpdateCanvasAssignmentBody(BaseModel):
    name: str | None
    available_date: datetime | None
    due_date: datetime | None

class CanvasService:
    def __init__(self, session: Session):
        self.session = session
        self.client = httpx.AsyncClient(
            base_url=f"{ self.api_url }",
            headers={
                "User-Agent": f"eduhelx_grader_api",
                "Authorization": f"Bearer { settings.CANVAS_API_KEY }"
            },
            timeout=httpx.Timeout(10)
        )

    @property
    def api_url(self) -> str:
        return settings.CANVAS_API_URL + ("/" if not settings.CANVAS_API_URL.endswith("/") else "")
    
    async def _make_request(self, method: str, endpoint: str, headers={}, **kwargs):
        res = await self.client.request(
            method,
            endpoint,
            headers={
                **headers
            },
            **kwargs
        )
        try:
            res.raise_for_status()
        except Exception as e:
            if hasattr(e, "response"):
                raise LMSBackendException(e.response.text) from e
            raise LMSBackendException(str(e)) from e
        return res.json()
    
    async def _get(self, endpoint: str, **kwargs):
        return await self._make_request("GET", endpoint, **kwargs)

    async def _post(self, endpoint: str, **kwargs):
        return await self._make_request("POST", endpoint, **kwargs)
    
    async def _put(self, endpoint: str, **kwargs):
        return await self._make_request("PUT", endpoint, **kwargs)
    
    async def _patch(self, endpoint: str, **kwargs):
        return await self._make_request("PATCH", endpoint, **kwargs)
    
    async def _delete(self, endpoint: str, **kwargs):
        return await self._make_request("DELETE", endpoint, **kwargs)

    async def get_courses(self):
        return await self._get("courses")

    async def get_course(self):
        return await self._get(f"courses/{ settings.CANVAS_COURSE_ID }")
    
    # returns a dictionary of assignments for a course
    async def get_assignments(self):
        return await self._get(f"courses/{ settings.CANVAS_COURSE_ID }/assignments")

    async def get_assignment(self, assignment_id):
        return await self._get(f"courses/{ settings.CANVAS_COURSE_ID }/assignments/{ assignment_id }")
    
    async def get_students(self):
        return await self.get_users(user_type=UserType.STUDENT)

    async def get_instructors(self):
        return await self.get_users(user_type=UserType.INSTRUCTOR)
    
    async def get_student_by_pid(self, pid: str):
        return await self.get_user_by_pid(pid, UserType.STUDENT)
    
    async def get_instructor_by_pid(self, pid: str):
        return await self.get_user_by_pid(pid, UserType.INSTRUCTOR)
    
    async def get_user_by_pid(self, pid: str, user_type: UserType):
        users = await self.get_users(user_type)
        for user in users:
            if user["sis_user_id"] == pid: return user
        raise LMSUserNotFoundException()

    async def get_users(self, user_type: UserType):
        if user_type == UserType.STUDENT:
            enrollment_type = "student"
        elif user_type == UserType.INSTRUCTOR:
            enrollment_type = "teacher"
        else:
            raise ValueError("You can only get student and instructor users from this endpoint")
        return await self._get(f"courses/{ settings.CANVAS_COURSE_ID }/users", params={
            "enrollment_type": enrollment_type
        })
    
    async def upload_grade(self, assignment_id: int, user_id: int, grade: float):
        url = f"courses/{ settings.CANVAS_COURSE_ID }/assignments/{ assignment_id }/submissions/{ user_id }"
        return await self._put(url, json={
            "submission": {
                "posted_grade": grade
            }
        })

    async def update_assignment(self, assignment_id: int, body: UpdateCanvasAssignmentBody):
        url = f"courses/{ settings.CANVAS_COURSE_ID }/assignments/{ assignment_id }"
        payload = body.dict(exclude_unset=True)
        if "available_date" in payload:
            unlock_at = payload.pop("available_date")
            payload["unlock_at"] = unlock_at.isoformat() if unlock_at is not None else None
        if "due_date" in payload:
            due_at = payload.pop("due_date")
            payload["due_at"] = due_at.isoformat() if due_at is not None else None
        return await self._put(url, json={
            "assignment": payload
        })

    async def get_onyen_from_pid(self, pid: str) -> UserModel:
        pid_onyen = self.session.query(OnyenPIDModel).filter_by(pid=pid).first()
        if pid_onyen is None:
            raise LMSUserNotFoundException(f'LMS user with pid "{ pid }" does not exist')
        return await UserService(self.session).get_user_by_onyen(pid_onyen.onyen)

    async def get_pid_from_onyen(self, onyen: str) -> str:
        pid_onyen = self.session.query(OnyenPIDModel).filter_by(onyen=onyen).first()
        if pid_onyen is None:
            raise LMSUserNotFoundException(f'LMS user with onyen "{ onyen }" does not exist')
        return pid_onyen.pid
    
    """ NOTE: Although you can modify an existing mapping directly via this method,
    I would recommend for clarity first calling unassociate_pid_from_user when modifying a mapping.
    If there's a chance the PID is already associated with a different user, this method will throw. """
    async def associate_pid_to_user(self, onyen: str, pid: str) -> None:
        with self.session.begin_nested():
            existing_mapping = self.session.query(OnyenPIDModel) \
                .filter((OnyenPIDModel.onyen == onyen) | (OnyenPIDModel.pid == pid)) \
                .first()
            
            if existing_mapping is not None:
                if existing_mapping.onyen == onyen and existing_mapping.pid == pid:
                    # Already associated, no further action required.
                    return
                
                elif existing_mapping.onyen == onyen:
                    # The Eduhelx user is currently associated with a different PID, update it.
                    existing_mapping.pid = pid
                    try:
                        self.session.flush()
                    except SQLAlchemyError as e:
                        DatabaseTransactionException.raise_exception(e)
                    return
                
                elif existing_mapping.pid == pid:
                    # This PID is already associated with a different Eduhelx user.
                    # We don't want to assume it's okay to unassociate them, that's the caller's job. 
                    raise LMSUserPIDAlreadyAssociatedException()
            
            else:
                self.session.add(OnyenPIDModel(onyen=onyen, pid=pid))
                try:
                    self.session.flush()
                except SQLAlchemyError as e:
                    DatabaseTransactionException.raise_exception(e)

        self.session.commit()
        
    async def unassociate_pid_from_user(self, onyen: str) -> None:
        with self.session.begin_nested():
            pid_onyen = self.session.query(OnyenPIDModel).filter_by(onyen=onyen).first()
            if pid_onyen is None:
                raise LMSUserNotFoundException()
            
            self.session.delete(pid_onyen)
            try:
                self.session.flush()
            except SQLAlchemyError as e:
                DatabaseTransactionException.raise_exception(e)
        
        self.session.commit()