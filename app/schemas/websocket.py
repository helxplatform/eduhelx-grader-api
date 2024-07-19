from typing import Optional
from uuid import uuid4
from pydantic import BaseModel, Field, UUID4
from app.events.schemas import CrudType, ResourceType

class WebsocketMessage(BaseModel):
    __event_name__: str
    uuid: UUID4 = Field(default_factory=uuid4)

class WebsocketErrorMessage(WebsocketMessage):
    exception: Exception
    originator: Optional[WebsocketMessage]

    class Config:
        arbitrary_types_allowed = True

class WebsocketCrudMessage(WebsocketMessage):
    __event_name__ = "crud_change"
    operation_type: CrudType
    resource_type: ResourceType
    resource: BaseModel