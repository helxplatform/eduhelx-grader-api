from fastapi import Depends
from fastapi_events.handlers.local import local_handler
from fastapi_events.typing import Event
from sqlalchemy.orm import Session

from .schemas import SyncEvents
from app.models import AssignmentModel
from app.events import ModifyAssignmentCrudEvent
from app.services import GiteaService, StudentService, CourseService
from app.core.dependencies import get_db_persistent

"""
NOTE: Use `get_db_persistent` instead of `get_db`. FastAPI-Events does not support generator-based DI.
You MUST call Session.close() once you are done with the database session. 
"""


@local_handler.register(event_name=ModifyAssignmentCrudEvent.__event_name__)
async def handle_sync_create_assignment(event: ModifyAssignmentCrudEvent, session: Session = Depends(get_db_persistent)):
    event_name, payload = event
    assignment = payload.assignment

    student_service = StudentService(session)
    course_service = CourseService(session)
    gitea_service = GiteaService(session)

    course = await course_service.get_course()
    students = await student_service.list_students()
    hook_content = await gitea_service.get_merge_control_hook()
    for student in students:
        student_repo_name = course_service._compute_student_repository_name(course.name)
        await GiteaService(session).set_git_hook(
            repository_name=student_repo_name,
            owner=student.onyen,
            hook_id="pre-receive",
            hook_content=hook_content
        )
    
    master_repository_name = await course_service.get_master_repository_name()
    instructor_organization_name = await course_service.get_instructor_gitea_organization_name()
    await GiteaService(session).set_git_hook(
        repository_name=master_repository_name,
        owner=instructor_organization_name,
        hook_id="pre-receive",
        hook_content=hook_content
    )

    session.close()