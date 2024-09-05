from typing import Optional
from enum import Enum
from pydantic import BaseModel

class CollaboratorPermission(str, Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"

class FileOperationType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

class FileOperation(BaseModel):
    # File content
    content: str
    # Path to file
    path: str
    # Rename an existing file
    from_path: Optional[str]
    operation: FileOperationType