from pydantic import BaseModel
from datetime import datetime
from .user import UserSchema

class InstructorSchema(UserSchema):
    class Config:
        orm_mode = True

class CreateInstructorSchema(BaseModel):
    onyen: str
    name: str
    email: str