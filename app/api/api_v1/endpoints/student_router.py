from typing import List
from pydantic import BaseModel
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.schemas import StudentSchema
from app.services import StudentService
from app.core.dependencies import get_db, PermissionDependency, StudentListPermission, StudentCreatePermission, UserIsStudentPermission

router = APIRouter()

class CreateStudentBody(BaseModel):
    onyen: str
    first_name: str
    last_name: str
    email: str

@router.get("/students/{onyen:str}", response_model=StudentSchema)
async def get_student(
    *,
    db: Session = Depends(get_db),
    perm: None = Depends(PermissionDependency(StudentListPermission)),
    onyen: str
):
    student = await StudentService(db).get_user_by_onyen(onyen)
    return student

@router.get("/students", response_model=List[StudentSchema])
async def list_students(
    *,
    db: Session = Depends(get_db),
    perm: None = Depends(PermissionDependency(StudentListPermission))
):
    students = await StudentService(db).list_students()
    return students

@router.put("/students/self/fork_cloned", response_model=None)
async def mark_fork_as_cloned(
    *,
    request: Request,
    db: Session = Depends(get_db),
    perm: None = Depends(PermissionDependency(UserIsStudentPermission))
):
    onyen = request.user.onyen
    student_service = StudentService(db)
    student = await student_service.get_user_by_onyen(onyen)
    await student_service.set_fork_cloned(student)
