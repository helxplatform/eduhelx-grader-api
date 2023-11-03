from typing import Optional, Any, Dict, List
from enum import Enum
from pydantic import BaseModel, BaseSettings, PostgresDsn, Json, validator, root_validator

class DevPhase(str, Enum):
    DEV = "dev"
    PROD = "prod"


class SetupWizardCourse(BaseModel):
    name: str

class SetupWizardInstructor(BaseModel):
    onyen: str
    first_name: str
    last_name: str
    email: str

class SetupWizardData(BaseModel):
    course: SetupWizardCourse
    instructors: List[SetupWizardInstructor]

class Settings(BaseSettings):
    # General config
    API_V1_STR: str = "/api/v1"
    DEV_PHASE: DevPhase = DevPhase.PROD
    DISABLE_AUTHENTICATION: bool = False

    # Setup wizard (JSON-serialized string)
    SETUP_WIZARD_DATA: Optional[SetupWizardData] = None

    # Gitea microservice
    GITEA_ASSIST_API_URL: str

    # Authentication
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRES_MINUTES: int = 30 # 30 minutes
    REFRESH_TOKEN_EXPIRES_MINUTES: int = 60 * 24 * 30 # 1 month

    # LDAP
    LDAP_HOST: str
    LDAP_PORT: int
    LDAP_SERVICE_ACCOUNT_BIND_DN: str
    LDAP_SERVICE_ACCOUNT_PASSWORD: str
    LDAP_TIMEOUT_SECONDS: int = 5

    # Database
    POSTGRES_HOST: str
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    SQLALCHEMY_DATABASE_URI: Optional[PostgresDsn] = None

    @validator("SQLALCHEMY_DATABASE_URI", pre=True)
    def assemble_db_connection(cls, v: Optional[str], values: Dict[str, Any]) -> Any:
        if isinstance(v, str): return v
        return PostgresDsn.build(
            scheme="postgresql",
            host=values.get("POSTGRES_HOST"),
            port=values.get("POSTGRES_PORT"),
            path="/" + values.get("POSTGRES_DB"),
            user=values.get("POSTGRES_USER"),
            password=values.get("POSTGRES_PASSWORD")
        )

    @root_validator
    def validate_mutually_exclusive(cls, values: Dict[str, Any]) -> Any:
        dev_phase = values.get("DEV_PHASE")
        disable_authentication = values.get("DISABLE_AUTHENTICATION")

        if disable_authentication and dev_phase == "PROD":
            raise ValueError("You cannot use DISABLE_AUTHENTICATION in production mode. Either enable authentication or set DEV_PHASE to DEV.")

        return values

    class Config:
        case_sensitive = True

settings = Settings()
