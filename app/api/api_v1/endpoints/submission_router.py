from typing import Dict, List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Request, Query, Depends
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from app.schemas import SubmissionSchema
from app.services import SubmissionService, StudentService, AssignmentService, GiteaService, CourseService, LmsSyncService
from app.models import SubmissionModel
from app.core.dependencies import get_db, PermissionDependency, UserIsStudentPermission, SubmissionCreatePermission, SubmissionListPermission, SubmissionDownloadPermission

router = APIRouter()

class SubmissionBody(BaseModel):
    assignment_id: int
    commit_id: str
    student_notebook_content: str

@router.post("/submissions", response_model=SubmissionSchema)
async def create_submission(
    *,
    request: Request,
    db: Session = Depends(get_db),
    perm: None = Depends(PermissionDependency(UserIsStudentPermission, SubmissionCreatePermission)),
    submission_body: SubmissionBody
):
    onyen = request.user.onyen

    submission_service = SubmissionService(db)
    student = await StudentService(db).get_user_by_onyen(onyen)
    assignment = await AssignmentService(db).get_assignment_by_id(submission_body.assignment_id)
    submission = await submission_service.create_submission(
        student,
        assignment,
        commit_id=submission_body.commit_id,
        student_notebook_content=submission_body.student_notebook_content.encode()
    )

    return await submission_service.get_submission_schema(submission)

@router.get("/submissions", response_model=List[SubmissionSchema] | Dict[str, List[SubmissionSchema]])
async def get_submissions(
    *,
    request: Request,
    db: Session = Depends(get_db),
    perm: None = Depends(PermissionDependency(SubmissionListPermission)),
    assignment_id: int,
    student_onyen: Optional[str] = Query(default=None, description="Student's onyen. Lists all students if omitted.")
):
    onyen = request.user.onyen
    submission_service = SubmissionService(db)
    assignment = await AssignmentService(db).get_assignment_by_id(assignment_id)
    if student_onyen is None:
        students = await StudentService(db).list_students()
        return { student.onyen : [
            await submission_service.get_submission_schema(s)
            for s in await submission_service.get_submissions(student, assignment)
        ] for student in students }
    else:
        student = await StudentService(db).get_user_by_onyen(student_onyen)
        return [
            await submission_service.get_submission_schema(s)
            for s in await submission_service.get_submissions(student, assignment)
        ]
    
@router.get("/submissions/self", response_model=List[SubmissionSchema])
async def get_own_submissions(
    *,
    request: Request,
    db: Session = Depends(get_db),
    perm: None = Depends(PermissionDependency(UserIsStudentPermission)),
    assignment_id: int
):
    onyen = request.user.onyen
    submission_service = SubmissionService(db)
    student = await StudentService(db).get_user_by_onyen(onyen)
    assignment = await AssignmentService(db).get_assignment_by_id(assignment_id)
    submissions = await submission_service.get_submissions(student, assignment)

    return [await submission_service.get_submission_schema(s) for s in submissions]

@router.get("/submissions/active", response_model=SubmissionSchema)
async def get_active_submission(
    *,
    db: Session = Depends(get_db),
    perm: None = Depends(PermissionDependency(SubmissionListPermission)),
    onyen: str,
    assignment_id: int
):
    submission_service = SubmissionService(db)

    student = await StudentService(db).get_user_by_onyen(onyen)
    assignment = await AssignmentService(db).get_assignment_by_id(assignment_id)
    submission = await submission_service.get_active_submission(student, assignment)

    return await submission_service.get_submission_schema(submission)
    
@router.get("/submissions/{submission_id}", response_model=SubmissionSchema)
async def get_submission_by_id(
    *,
    request: Request,
    db: Session = Depends(get_db),
    perm: None = Depends(PermissionDependency(SubmissionListPermission)),
    submission_id: int
):
    submission_service = SubmissionService(db)
    submission = await submission_service.get_submission_by_id(submission_id)
    return await submission_service.get_submission_schema(submission)

async def download_submission_stream(db, submission: SubmissionModel):
    gitea_service = GiteaService(db)
    course_service = CourseService(db)

    student = submission.student
    student_repo_name = await course_service.get_student_repository_name(student.onyen)

    archive_name = f"assn{ submission.assignment_id }-{ student.onyen }-subm{ submission.id }.zip"
    archive_stream = await gitea_service.download_repository(
        name=student_repo_name,
        owner=student.onyen,
        treeish_id=submission.commit_id,
        path=submission.assignment.directory_path
    )
    return StreamingResponse(
        archive_stream,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{ archive_name }"'}
    )

@router.get("/submissions/active/download", response_class=FileResponse)
async def download_active_submission(
    *,
    db: Session = Depends(get_db),
    perm: None = Depends(PermissionDependency(SubmissionListPermission, SubmissionDownloadPermission)),
    onyen: str,
    assignment_id: int
):
    student = await StudentService(db).get_user_by_onyen(onyen)
    assignment = await AssignmentService(db).get_assignment_by_id(assignment_id)
    active_submission = await SubmissionService(db).get_active_submission(student, assignment)
    return await download_submission_stream(db, active_submission)

@router.get("/submissions/{submission_id}/download", response_class=FileResponse)
async def download_submission(
    *,
    db: Session = Depends(get_db),
    perm: None = Depends(PermissionDependency(SubmissionListPermission, SubmissionDownloadPermission)),
    submission_id: int
):
    submission = await SubmissionService(db).get_submission_by_id(submission_id)
    return await download_submission_stream(db, submission)