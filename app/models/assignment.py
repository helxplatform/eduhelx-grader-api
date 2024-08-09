from pathlib import Path
from sqlalchemy import (
    Column, Sequence, Boolean,
    Integer, Text, DateTime,
    func
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from app.database import Base

class AssignmentModel(Base):
    __tablename__ = "assignment"

    id = Column(Integer, Sequence("assignment_id_seq"), primary_key=True, index=True)
    name = Column(Text, nullable=False, unique=True)
    directory_path = Column(Text, nullable=False)
    # Relative to the assignment root (directory_path), i.e., the fully qualified path
    # of the file within the repo is `/{directory_path}/{master_notebook_path}`
    master_notebook_path = Column(Text, nullable=False)
    grader_question_feedback = Column(Boolean, server_default='t', nullable=False)
    created_date = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    available_date = Column(DateTime(timezone=True))
    due_date = Column(DateTime(timezone=True))
    last_modified_date = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    is_published = Column(Boolean, server_default='f', nullable=False)
    
    @hybrid_property
    def student_notebook_path(self) -> str:
        p = Path(self.master_notebook_path)
        return str(p.parents[0] / (p.stem + "-student.ipynb"))