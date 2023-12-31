from typing import List
from pydantic import BaseModel
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.schemas import RefreshTokenSchema, UserRoleSchema, UserPermissionSchema
from app.services import UserService, JwtService
from app.core.dependencies import get_db, PermissionDependency, RequireLoginPermission

router = APIRouter()

class LoginBody(BaseModel):
    onyen: str
    autogen_password: str

class RefreshBody(BaseModel):
    refresh_token: str
    

@router.post("/login", response_model=RefreshTokenSchema)
async def login(
    *,
    db: Session = Depends(get_db),
    login_body: LoginBody
):
    token = await UserService(db).login(login_body.onyen, login_body.autogen_password)
    return token

@router.post("/refresh", response_model=str)
async def refresh(
    *,
    db: Session = Depends(get_db),
    refresh_body: RefreshBody
):
    token = await JwtService().refresh_access_token(refresh_body.refresh_token)
    return token

@router.get("/role/self", response_model=UserRoleSchema)
async def get_role(
    *,
    request: Request,
    db: Session = Depends(get_db),
    perm: None = Depends(PermissionDependency(RequireLoginPermission)),
):
    onyen = request.user.onyen
    user = await UserService(db).get_user_by_onyen(onyen)
    return UserRoleSchema(
        name=user.role.name,
        permissions=[UserPermissionSchema(name=p.value) for p in user.role.permissions]
    )