import enum
from sqlalchemy import Column, Sequence, Integer, Text, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.core.role_permissions import UserPermission, UserRoleType

class UserType(enum.Enum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"

class UserModel(Base):
    __tablename__ = "user_account"
    
    id = Column(Integer, Sequence("user_account_id_seq"), primary_key=True, autoincrement=True, index=True)
    user_type = Column(Enum(UserType), nullable=False)

    onyen = Column(Text, nullable=False, unique=True, index=True)
    name = Column(Text, nullable=False)
    email = Column(Text, nullable=False, unique=True)

    role = Column(UserRoleType, nullable=False)

    autogen_password_auth = relationship("AutoPasswordAuthModel", cascade="all,delete", uselist=False)
    onyen_pid = relationship("OnyenPIDModel", cascade="all,delete", uselist=False)

    __mapper_args__ = {
        "polymorphic_on": "user_type",
        "polymorphic_identity": "user"
    }

    def has_permission(self, permission: UserPermission) -> bool:
        return permission in self.role.permission
    
    def has_access(self, resource) -> bool:
        raise NotImplementedError("TODO") # HLXK-288