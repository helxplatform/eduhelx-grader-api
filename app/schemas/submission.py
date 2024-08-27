from datetime import datetime
from pydantic import BaseModel
from .user import StudentSchema
from .assignment import AssignmentSchema

class DatabaseSubmissionSchema(BaseModel):
    id: int
    commit_id: str | None
    graded: bool
    submission_time: datetime
    is_gradable: bool

    class Config:
        orm_mode = True

class SubmissionSchema(DatabaseSubmissionSchema):
    active: bool