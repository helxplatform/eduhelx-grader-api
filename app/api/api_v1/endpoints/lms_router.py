from typing import List
from pydantic import BaseModel
from fastapi import APIRouter, Request, Depends, UploadFile, File
from sqlalchemy.orm import Session
from app.services import LmsSyncService, AssignmentService
from app.core.dependencies import (
    get_db, PermissionDependency,
    UserIsInstructorPermission
)

router = APIRouter()

class GradeUpload(BaseModel):
    onyen: str
    percent_correct: int

class UploadGradesBody(BaseModel):
    grades: List[GradeUpload]

@router.get("/lms/downsync")
async def downsync(
    *,
    db: Session = Depends(get_db),
    perm: None = Depends(PermissionDependency(UserIsInstructorPermission))
):
    return await LmsSyncService(db).downsync()

@router.get("/lms/downsync/students")
async def downsync_students(
    *,
    db: Session = Depends(get_db),
    perm: None = Depends(PermissionDependency(UserIsInstructorPermission))
):
    return await LmsSyncService(db).sync_students()

@router.get("/lms/downsync/assignments")
async def downsync_assignments(
    *,
    db: Session = Depends(get_db),
    perm: None = Depends(PermissionDependency(UserIsInstructorPermission))
):
    return await LmsSyncService(db).sync_assignments()

@router.post("/lms/grades/{assignment_id}")
async def post_grades(
    *,
    db: Session = Depends(get_db),
    assignment_id: int,
    perm: None = Depends(PermissionDependency(UserIsInstructorPermission)),
    body: UploadGradesBody
):
    # Validate the assignment exists
    await AssignmentService(db).get_assignment_by_id(assignment_id)
    return await LmsSyncService(db).upload_grades(assignment_id, [grade.dict() for grade in body.grades])