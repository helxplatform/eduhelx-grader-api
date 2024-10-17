import requests
import httpx
import os.path
from typing import BinaryIO
from pathlib import Path
from enum import Enum
from urllib.parse import urlparse
from pydantic import BaseModel, PositiveInt
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.config import settings
from app.enums.canvas.canvas_workflow_state_filter import CanvasWorkflowStateFilter
from app.models import UserModel, OnyenPIDModel
from app.services import UserService, UserType
from app.core.utils.datetime import get_now_with_tzinfo
from app.core.exceptions import (
    LMSUserNotFoundException, LMSUserPIDAlreadyAssociatedException, LMSBackendException,
    LMSFolderNotFoundException, LMSFileUploadException
)

class DuplicateFileAction(str, Enum):
    OVERWRITE = "overwrite"
    RENAME = "rename"

class UpdateCanvasAssignmentBody(BaseModel):
    name: str | None
    available_date: datetime | None
    due_date: datetime | None
    max_attempts: PositiveInt | None
    is_published: bool | None

class CanvasService:
    def __init__(self, db: Session):
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {settings.CANVAS_API_KEY}"
        })
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
    
    async def _check_response(self, res: httpx.Response):
        try:
            res.raise_for_status()
        except Exception as e:
            if hasattr(e, "response"):
                raise LMSBackendException(e.response.text, e.response) from e
            raise LMSBackendException(str(e)) from e
    
    async def _make_request(self, method: str, endpoint: str, headers={}, **kwargs):
        res = await self.client.request(
            method,
            endpoint,
            headers={
                **headers
            },
            **kwargs
        )
        await self._check_response(res)
        return res.json()
    
    async def _get(self, endpoint: str, **kwargs):
        if 'params' not in kwargs:
            kwargs['params'] = {}
        
        # Set or override the 'per_page' parameter to 100
        kwargs['params']['per_page'] = 100

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
    
    """ NOTE: Will return a Submission for every specified student_id, even if they have not submitted (submitted_at = None). """
    """ NOTE: include_submission_history includes the returned Submission as its final element. """
    async def _get_submissions_for_assignments(
        self,
        # Return submissions for all assignments if not provided
        assignment_ids: list[int] | None,
        student_ids: list[int],
        *,
        # Note: I believe submission_history generally includes the active submission as well.
        include_submission_history: bool = True,
        include_comments: bool = False,
        include_rubric_assessment: bool = False,
        include_visibility: bool = False,
        include_is_read: bool = False,
        workflow_state_filter: CanvasWorkflowStateFilter | None = None
    ):
        include = []
        if include_submission_history: include.append("submission_history")
        if include_comments: include.append["submission_comments"]
        if include_rubric_assessment: include.append["full_rubric_assessment"]
        if include_visibility: include.append("visibility")
        if include_is_read: include.append("read_status")

        params = {
            "student_ids[]": student_ids,
            "include[]": include,
        }
        if assignment_ids is not None: params["assignment_ids[]"] = assignment_ids

        if workflow_state_filter is not None:
            params["workflow_state"] = workflow_state_filter.value
        return await self._get(f"courses/{ settings.CANVAS_COURSE_ID }/students/submissions", params=params)

    """ NOTE: If student_id is provided, returns a single Submission object. """
    """ NOTE: Otherwise, returns a Submission for every enrolled student, even if they have not submitted (submitted_at = None). """
    """ NOTE: include_submission_history includes the returned Submission as its final element. """
    async def get_submissions(
        self,
        assignment_id: int,
        student_id: int | None = None,
        **kwargs
    ):
        student_ids = [student_id] if student_id is not None else []
        submissions = await self._get_submissions_for_assignments([assignment_id], student_ids, **kwargs)
        if student_id is not None: return submissions[0]
        return submissions
    
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
    
    async def _upload_file(
        self,
        upload_url: str,
        file: BinaryIO,
        parent_folder_path_or_id: Path | str | int | None = None,
        on_duplicate: DuplicateFileAction = DuplicateFileAction.OVERWRITE
    ):
        use_id = isinstance(parent_folder_path_or_id, int)
        use_path = isinstance(parent_folder_path_or_id, (str, Path))
        
        # Seek to end of file buffer
        file.seek(0, 2)
        payload = {
            "name": file.name,
            "size": file.tell(),
            "content_type": "",
            "no_redirect": True,
            "on_duplicate": on_duplicate.value
        }
        
        if use_id: payload["parent_folder_id"] = parent_folder_path_or_id
        if use_path: payload["parent_folder_path"] = str(parent_folder_path_or_id)
        
        data = await self._post(upload_url, json=payload)
        upload_url = data["upload_url"]
        file_param = data.get("file_param", file)

        file.seek(0)
        res = await self.client.post(upload_url, data=data["upload_params"], files={
            file_param: (file.name, file.read())
        })
        
        await self._check_response(res)

        canvas_image_url = res.headers.get("location")

        if res.status_code >= 300 and res.status_code < 400:
            # If a redirect is returned, you are supposed to GET the redirect to confirm the upload.
            # We can't do this though since we can't access the file on behalf of the user...
            raise LMSFileUploadException("file upload returned confirmation redirect, which is currently unsupported")
        
        # VERY HACKY, no other choice...
        try:
            return int(urlparse(canvas_image_url).path.split("/")[-1])
        except Exception as e:
            raise LMSFileUploadException(str(e)) from e
        

        """ NOTE: The file access endpoint (which is the value of canvas_image_url) can only be used by the owner of the file.
        Until we can masquerade as the user (this permission can be granted to admin accounts) we can use the proper workflow.
        """
        # if res.status_code >= 300 and res.status_code < 400:
        #     # Upload is incomplete, need to perform a GET request to returned URL first.
        #     res = await self.client.get(image_url)
        #     await self._check_response(res)
        
        # return await self._post(image_url, headers={
        #     "Content-Length": "0"
        # })
    
    """ Not working at the moment.
    async def upload_user_file(
        self,
        user_id: int,
        file: BinaryIO,
        parent_folder_path_or_id: str | int,
        on_duplicate: DuplicateFileAction = DuplicateFileAction.OVERWRITE
    ):
        url = f"users/{ user_id }/files"
        return await self._upload_file(
            url,
            file,
            parent_folder_path_or_id,
            on_duplicate
        )
    """
    
    async def upload_course_file(
        self,
        file: BinaryIO,
        parent_folder_path_or_id: str | int,
        on_duplicate: DuplicateFileAction = DuplicateFileAction.OVERWRITE
    ):
        url = f"courses/{ settings.CANVAS_COURSE_ID }/files"
        return await self._upload_file(
            url,
            file,
            parent_folder_path_or_id,
            on_duplicate
        )
    
    """ NOTE: Currently, UNC Canvas does not allow uploading a submission file on behalf of another user """
    async def upload_submission_file(
        self,
        assignment_id: int,
        user_id: int,
        file: BinaryIO,
        on_duplicate: DuplicateFileAction = DuplicateFileAction.OVERWRITE
    ):
        url = f"courses/{ settings.CANVAS_COURSE_ID }/assignments/{ assignment_id }/submissions/{ user_id }/files"
        return await self._upload_file(
            url,
            file,
            on_duplicate=on_duplicate
        )
    
    async def get_course_folder(
        self,
        folder_path: str | Path
    ):
        folder_path = Path(folder_path)
        url = f"courses/{ settings.CANVAS_COURSE_ID }/folders"
        folders = await self._get(url)
        for folder in folders:
            # Canvas files are always under a hidden top-level directory.
            # E.g., course files are under the "course files" directory, but you don't see that in the UI.
            # We're have to remove that from the path before comparing.
            path = Path(folder["full_name"])
            if len(path.parts) <= 1: continue
            path = Path(*path.parts[1:])
            if path == folder_path: return folder
        raise LMSFolderNotFoundException(f'Could not find the folder "{ folder_path }" in Canvas course files')
    
    async def _create_folder(
        self,
        upload_url: str,
        name: str,
        parent_folder_path_or_id: str | int,
        hidden: bool,
        locked: bool,
    ):
        use_id = isinstance(parent_folder_path_or_id, int)
        payload = {
            "name": name,
            "hidden": hidden,
            "locked": locked
        }
        if use_id: payload["parent_folder_id"] = parent_folder_path_or_id
        else: payload["parent_folder_path"] = parent_folder_path_or_id

        return await self._post(upload_url, json=payload)
    
    async def create_course_folder(
        self,
        name: str,
        parent_folder_path_or_id: str | int,
        hidden: bool = False,
        locked: bool = False
    ):
        url = f"courses/{ settings.CANVAS_COURSE_ID }/folders"
        return await self._create_folder(
            url,
            name,
            parent_folder_path_or_id,
            hidden,
            locked
        )
    
    async def upload_submission(
        self,
        assignment_id: int,
        user_id: int,
        student_notebook: BinaryIO,
        comments: str | None = None
    ):
        url = f"courses/{ settings.CANVAS_COURSE_ID }/assignments/{ assignment_id }/submissions"
        iso_now = get_now_with_tzinfo().isoformat()

        assignment = await self.get_assignment(assignment_id)
        student_course_submissions_folder = await self.get_student_course_submissions_folder_path()
        await self.upload_course_file(
            student_notebook,
            os.path.join(student_course_submissions_folder, assignment["name"]),
            on_duplicate=DuplicateFileAction.OVERWRITE
        )
        student_notebook_file_id = await self.upload_submission_file(
            assignment_id,
            user_id,
            student_notebook,
            on_duplicate=DuplicateFileAction.OVERWRITE
        )
        
        payload = {
            "submission": {
                "user_id": user_id,
                "submission_type": "online_upload",
                "file_ids": [student_notebook_file_id],
                "submitted_at": iso_now
            },
            "comment": {}
        }
        if comments is not None: payload["comment"]["text_comment"] = comments

        await self._post(url, json=payload)

    """
    Note that Canvas does not support associating grades with submissions.
    You can only set the overall assignment grade for the student.
    Comments will be attached to the active submission.
    """
    async def upload_assignment_grade(
        self,
        assignment_id: int,
        user_id: int,
        # between [0,1]
        grade_proportion: float,
        comments: str | None = None,
    ):
        url = f"courses/{ settings.CANVAS_COURSE_ID }/assignments/{ assignment_id }/submissions/{ user_id }"
        
        posted_grade = f"{ grade_proportion * 100 }%"

        payload = {
            "submission": {
                "user_id": user_id,
                "posted_grade": posted_grade
            },
            "comment": {}
        }
        if comments is not None: payload["comment"]["text_comment"] = comments

        await self._put(url, json=payload)

    async def update_assignment(self, assignment_id: int, body: UpdateCanvasAssignmentBody):
        url = f"courses/{ settings.CANVAS_COURSE_ID }/assignments/{ assignment_id }"
        payload = body.dict(exclude_unset=True)
        if "available_date" in payload:
            unlock_at = payload.pop("available_date")
            payload["unlock_at"] = unlock_at.isoformat() if unlock_at is not None else None
        if "due_date" in payload:
            due_at = payload.pop("due_date")
            payload["due_at"] = due_at.isoformat() if due_at is not None else None
        if "max_attempts" in payload:
            allowed_attempts = payload.pop("max_attempts")
            payload["allowed_attempts"] = allowed_attempts if allowed_attempts is not None else -1
        return await self._put(url, json={
            "assignment": payload
        })

    async def get_onyen_from_pid(self, pid: str) -> UserModel:
        pid_onyen = self.db.query(OnyenPIDModel).filter_by(pid=pid).first()
        if pid_onyen is None:
            raise LMSUserNotFoundException(f'LMS user with pid "{ pid }" does not exist')
        return await UserService(self.db).get_user_by_onyen(pid_onyen.onyen)

    async def get_pid_from_onyen(self, onyen: str) -> str:
        pid_onyen = self.db.query(OnyenPIDModel).filter_by(onyen=onyen).first()
        if pid_onyen is None:
            raise LMSUserNotFoundException(f'LMS user with onyen "{ onyen }" does not exist')
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
                raise LMSUserPIDAlreadyAssociatedException()
        else:
            self.db.add(OnyenPIDModel(onyen=onyen, pid=pid))
            self.db.commit()
        
    async def unassociate_pid_from_user(self, onyen: str) -> None:
        pid_onyen = self.db.query(OnyenPIDModel).filter_by(onyen=onyen).first()
        if pid_onyen is None:
            raise LMSUserNotFoundException()
        self.db.delete(pid_onyen)
        self.db.commit()

    async def get_private_course_folder_path(self) -> str:
        return self._compute_private_course_folder_path()
    
    async def get_student_course_submissions_folder_path(self) -> str:
        return self._compute_student_course_submissions_folder_path(await self.get_private_course_folder_path())

    @staticmethod
    def _compute_private_course_folder_path() -> str:
        return "EduHeLx Hidden Files"
    
    @staticmethod
    def _compute_student_course_submissions_folder_path(private_course_folder_path: str):
        return os.path.join(private_course_folder_path, "Student Submissions")