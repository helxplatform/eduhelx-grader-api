import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models import UserModel, OnyenPIDModel
from app.services import UserService
from app.core.exceptions import (
    LMSNoCourseFetchedException, LMSNoAssignmentFetchedException, LMSNoStudentsFetchedException,
    LMSUserNotFoundException, LMSUserPIDAlreadyAssociated
)
# # Assuming we'll store our Canvas LMS API key securely, for now I am just hard coding it
# CANVAS_API_KEY = "7006~RMJbYVaRDn3SeKt3kekSHJ1RaVk5oLbmDjkxg650f2rQ6MXwHoeAl3xiWO2rtnzZ"
# CANVAS_API_URL = "https://uncch.instructure.com/api/v1"
class CanvasService:
    def __init__(self, db: Session):
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {settings.CANVAS_API_KEY}"})

    async def get_courses(self):
        try:
            url = f"{settings.CANVAS_API_URL}/courses"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        
        except requests.RequestException as e:
            raise LMSNoCourseFetchedException()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)
        )

    async def get_course(self, additional_params=None):
        try:
            url = f"{settings.CANVAS_API_URL}/courses/{settings.CANVAS_COURSE_ID}"
            
            if additional_params:
                # Append additional parameters to the URL
                url += "?" + "&".join([f"{key}={value}" for key, value in additional_params.items()])
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        
        except requests.RequestException as e:
            raise LMSNoCourseFetchedException()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # returns a dictionary of assignments for a course
    async def get_assignments(self):
        try:
            url = f"{settings.CANVAS_API_URL}/courses/{settings.CANVAS_COURSE_ID}/assignments"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        
        except requests.RequestException as e:
            raise LMSNoAssignmentFetchedException()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def get_assignment(self, assignment_id):
        try:
            url = f"{settings.CANVAS_API_URL}/courses/{settings.CANVAS_COURSE_ID}/assignments/{assignment_id}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        
        except requests.RequestException as e:
            raise LMSNoAssignmentFetchedException()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def get_users(self, additional_params=None):
        try:
            url = f"{settings.CANVAS_API_URL}/courses/{settings.CANVAS_COURSE_ID}/users"

            if additional_params:
                # Append additional parameters to the URL
                url += "?" + "&".join([f"{key}={value}" for key, value in additional_params.items()])

            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        
        except requests.RequestException as e:
            raise LMSNoStudentsFetchedException()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def upload_grades(self, assignment_id: int, login_id: str, grade: float):
        try:
            url = f"{settings.CANVAS_API_URL}/courses/{settings.CANVAS_COURSE_ID}/assignments/{assignment_id}/submissions?login_id={login_id}"
            response = self.session.put(url, json={"grade": grade})
            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) 

    async def get_onyen_from_pid(self, pid: str) -> UserModel:
        pid_onyen = self.db.query(OnyenPIDModel).filter_by(pid=pid).first()
        if pid_onyen is None:
            raise LMSUserNotFoundException()
        return await UserService(self.db).get_user_by_onyen(pid_onyen.onyen)

    async def get_pid_from_onyen(self, onyen: str) -> str:
        pid_onyen = self.db.query(OnyenPIDModel).filter_by(onyen=onyen).first()
        if pid_onyen is None:
            raise LMSUserNotFoundException()
        return pid_onyen.pid
    
    """ NOTE: Although you can modify an existing mapping directly via this method,
    I would recommend for clarity first calling unassociate_pid_from_user when modifying a mapping.
    If there's a chance the PID is already associated with a different user, this method will throw. """
    async def associate_pid_to_user(self, onyen: str, pid: str) -> None:
        existing_mapping = self.db.query(OnyenPIDModel).filter((OnyenPIDModel.onyen == onyen) | (OnyenPIDModel.pid == pid)).first()
        if existing_mapping is not None:
            if existing_mapping.onyen == onyen and existing_mapping.pid == pid:
                # Already associated, no further action required.
                return
            elif existing_mapping.onyen == onyen:
                # The Eduhelx user is currently associated with a different PID, update it.
                existing_mapping.pid = pid
                self.db.commit()
                return
            elif existing_mapping.pid == pid:
                # This PID is already associated with a different Eduhelx user.
                # We don't want to assume it's okay to unassociate them, that's the caller's job. 
                raise LMSUserPIDAlreadyAssociated()
        else:
            self.db.add(OnyenPIDModel(onyen=onyen, pid=pid))
            self.db.commit()
        
    async def unassociate_pid_from_user(self, onyen: str) -> None:
        pid_onyen = self.db.query(OnyenPIDModel).filter_by(onyen=onyen).first()
        if pid_onyen is None:
            raise LMSUserNotFoundException()
        self.db.delete(pid_onyen)
        self.db.commit()