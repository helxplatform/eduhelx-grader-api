from typing import List
from datetime import datetime, timedelta
from pydantic import BaseModel
from ._unset import UNSET

class AssignmentSchema(BaseModel):
    id: int
    name: str
    directory_path: str
    # Relative to the assignment root (directory_path), i.e., the fully qualified path
    # of the file within the repo is `/{directory_path}/{master_notebook_path}`
    master_notebook_path: str
    # Relative to the assignment root (directory_path)
    student_notebook_path: str
    grader_question_feedback: bool
    created_date: datetime
    available_date: datetime | None
    due_date: datetime | None
    last_modified_date: datetime
    is_published: bool

    class Config:
        orm_mode = True

class UpdateAssignmentSchema(BaseModel):
    name: str = UNSET
    directory_path: str = UNSET
    master_notebook_path: str = UNSET
    grader_question_feedback: bool = UNSET
    available_date: datetime | None
    due_date: datetime | None
    is_published: bool = UNSET

# Adds in fields relevant for JLP (tailored to the professor)
class InstructorAssignmentSchema(AssignmentSchema):
    is_available: bool
    is_closed: bool

# Adds in student-specific fields to the assignment (tailored to a particular student)
class StudentAssignmentSchema(AssignmentSchema):
    adjusted_available_date: datetime | None
    adjusted_due_date: datetime | None
    is_available: bool
    is_closed: bool
    # Release date is deferred to a later date for the student
    is_deferred: bool
    # Due date is extended to a later date for the student
    is_extended: bool