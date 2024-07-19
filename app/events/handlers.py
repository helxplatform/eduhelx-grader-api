from fastapi import Depends
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import AssignmentModel
from app.events.schemas import AssignmentCrudEvent
from app.events.emitter import event_emitter
from app.core.dependencies import get_db_persistent

"""
NOTE: Keep in mind that exceptions raised in event handlers bubble up to the original emitter.
If it's okay for the handler to fail, then the handler should catch the error instead of raising it.
"""

@event_emitter.on("crud:assignment:*")
async def handle_master_repo_hook_update(event: AssignmentCrudEvent):
    from app.services import GiteaService, StudentService, CourseService
    
    assignment = event.assignment

    with SessionLocal() as session:
        course_service = CourseService(session)
        gitea_service = GiteaService(session)

        hook_content = await gitea_service.get_merge_control_hook()    
        master_repository_name = await course_service.get_master_repository_name()
        instructor_organization_name = await course_service.get_instructor_gitea_organization_name()

        await GiteaService(session).set_git_hook(
            repository_name=master_repository_name,
            owner=instructor_organization_name,
            hook_id="pre-receive",
            hook_content=hook_content
        )