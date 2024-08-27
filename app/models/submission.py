from sqlalchemy import (
    Column, Sequence, ForeignKey,
    Integer, String, DateTime,
    Boolean, func
)
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.hybrid import hybrid_property
from app.database import Base

class SubmissionModel(Base):
    __tablename__ = "submission"

    id = Column(Integer, Sequence("submission_id_seq"), primary_key=True, autoincrement=True, index=True)
    student_id = Column(Integer, ForeignKey("student.id"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignment.id"), nullable=False)
    commit_id = Column(String(255), nullable=True)
    graded = Column(Boolean(), server_default="f", nullable=False)
    submission_time = Column(DateTime(timezone=True), server_default=func.current_timestamp())

    student = relationship("StudentModel", foreign_keys="SubmissionModel.student_id", back_populates="submissions")
    assignment = relationship(
        "AssignmentModel",
        foreign_keys="SubmissionModel.assignment_id",
        backref=backref("submissions", cascade="all,delete")
    )

    @hybrid_property
    def is_gradable(self):
        return self.commit_id is not None