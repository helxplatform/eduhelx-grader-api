from typing import List, Annotated
from pydantic import BaseModel
from fastapi import APIRouter, Request, Depends, Header
from sqlalchemy.orm import Session
from app.schemas import RefreshTokenSchema, UserRoleSchema, UserPermissionSchema
from app.services import UserService, JwtService, AppstoreService, GiteaService
from app.models.user import UserType
from app.core.dependencies import get_db, PermissionDependency, RequireLoginPermission
from app.core.exceptions import UserNotFoundException, AppstoreUserDoesNotMatchException

router = APIRouter()

class LoginBody(BaseModel):
    onyen: str
    autogen_password: str

class AppstoreLoginBody(BaseModel):
    user_type: UserType

class SetGiteaSSHBody(BaseModel):
    # Name of the key
    name: str
    # Public key
    key: str

class DeleteGiteaSSHBody(BaseModel):
    name: str

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

@router.post("/login/appstore", response_model=RefreshTokenSchema, description="Authenticate via Appstore session (DOES NOT WORK IN SWAGGER UI)")
async def appstore_login(
    *,
    db: Session = Depends(get_db),
    appstore_access_token: Annotated[str, Header(description="Your sessionid for Appstore")],
    login_body: AppstoreLoginBody
):
    appstore_service = AppstoreService(db, appstore_access_token, login_body.user_type)
    user = await appstore_service.get_associated_eduhelx_user()
    # If the user is authenticated in appstore with a corresponding onyen, we can create a token for them.
    token = await UserService(db).create_user_token(user)
    return token
        
@router.put("/login/gitea/ssh", description="Set an SSH key for your Gitea user")
async def set_gitea_ssh(
    *,
    request: Request,
    db: Session = Depends(get_db),
    ssh_body: SetGiteaSSHBody,
):
    await GiteaService(db).set_ssh_key(request.user.onyen, ssh_body.name, ssh_body.key)

@router.delete("/logout/gitea/ssh", description="Remove an SSH key for your Gitea user")
async def set_gitea_ssh(
    *,
    request: Request,
    db: Session = Depends(get_db),
    ssh_body: DeleteGiteaSSHBody,
):
    await GiteaService(db).remove_ssh_key(request.user.onyen, ssh_body.name)

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