from fastapi import APIRouter
from .endpoints import (
    submission_router, assignment_router, user_router,
    student_router, instructor_router, course_router,
    settings_router, auth_router, lms_router, websocket_router
)

api_router = APIRouter()
api_router.include_router(submission_router.router, tags=["submissions"])
api_router.include_router(assignment_router.router, tags=["assignments"])
api_router.include_router(user_router.router, tags=["users"])
api_router.include_router(student_router.router, tags=["students"])
api_router.include_router(instructor_router.router, tags=["instructors"])
api_router.include_router(course_router.router, tags=["course"])
api_router.include_router(settings_router.router, tags=["settings"])
api_router.include_router(auth_router.router, tags=["auth"])
api_router.include_router(lms_router.router, tags=["lms"])
api_router.include_router(websocket_router.router, tags=["websockets"])