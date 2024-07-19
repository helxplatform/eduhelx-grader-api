from typing import List
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware import Middleware
from fastapi_pagination import add_pagination
from starlette.middleware.cors import CORSMiddleware

from app.api.api_v1 import api_router
from app.core.config import settings, DevPhase
from app.core.middleware import AuthenticationMiddleware, AuthBackend, LogMiddleware
from eduhelx_utils.custom_logger import CustomizeLogger
from app.core.exceptions import CustomException

import logging
from pathlib import Path

def init_routers(app: FastAPI):
    app.include_router(api_router, prefix=settings.API_V1_STR)

def init_listeners(app: FastAPI):
    @app.exception_handler(CustomException)
    async def custom_exception_handler(request: Request, exc: CustomException):
        content = { "error_code": exc.error_code, "message": exc.message }
        if settings.DEV_PHASE == DevPhase.DEV:
            content["stack"] = exc.stack
        return JSONResponse(
            status_code=exc.code,
            content=content,
        )
    
def init_monkeypatch():
    ### Monkey patch serializers for custom types
    from pydantic.json import ENCODERS_BY_TYPE
    from app.schemas._unset import _UNSET
    ENCODERS_BY_TYPE[_UNSET] = lambda _: None

def on_auth_error(request: Request, exc: Exception):
    status_code, error_code, message = 401, None, str(exc)
    if isinstance(exc, CustomException):
        status_code = int(exc.code)
        error_code = exc.error_code
        message = exc.message
    return JSONResponse(
        status_code=status_code,
        content={"error_code": error_code, "message": message}
    )

def make_middleware() -> List[Middleware]:
    return [
        *([Middleware(
            CORSMiddleware,
            allow_credentials=True,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"]
        )] if settings.DEV_PHASE == DevPhase.DEV else []),
        Middleware(
            AuthenticationMiddleware,
            backend=AuthBackend(),
            on_error=on_auth_error
        )
    ]


logger = logging.getLogger(__name__)
config_path=Path(__file__).with_name("logging_config.json")

def create_app() -> FastAPI:
    app = FastAPI(
        openapi_url=f"{ settings.API_V1_STR }/openapi.json",
        middleware=make_middleware()
    )
    logger = CustomizeLogger.make_logger(config_path)
    app.logger = logger
    app.add_middleware(LogMiddleware)
    init_monkeypatch()
    init_routers(app)
    init_listeners(app)
    add_pagination(app)
    
    return app

app = create_app()
