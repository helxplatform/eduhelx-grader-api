from fastapi import Depends
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import AssignmentModel
from app.events.schemas import CrudEvent, AssignmentCrudEvent
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

""" Ideally, we'd use `crud:*` here, but for some reason pymitter doesn't support higher-level wildcards... """
@event_emitter.on_any()
async def handle_crud_operation(event: CrudEvent):
    from app.services import (
        WebsocketManagerService, CourseService, UserService,
        StudentAssignmentService, InstructorAssignmentService,
    )
    from app.models.user import UserModel, UserType
    from app.schemas import WebsocketCrudMessage, AssignmentSchema, StudentSchema, InstructorSchema, SubmissionSchema
    from app.events.schemas import (
        ResourceType, CourseCrudEvent, AssignmentCrudEvent, UserCrudEvent, SubmissionCrudEvent
    )

    if not isinstance(event, CrudEvent): return

    with SessionLocal() as session:
        websocket_service = WebsocketManagerService(session)
        connected_users = await websocket_service.get_connected_users()

        # TODO: Verify user permissions
        # Permission system needs a bit of work with owned resources first though (HLXK-288)
        for user in connected_users:
            if user.user_type != UserType.STUDENT and user.user_type != UserType.INSTRUCTOR:
                continue

            if event.resource_type == ResourceType.COURSE:
                resource = await CourseService(session).get_course_with_instructors_schema()

            elif event.resource_type == ResourceType.ASSIGNMENT:
                if user.user_type == UserType.STUDENT:
                    resource = await StudentAssignmentService(session, user, event.assignment) \
                        .get_student_assignment_schema()
                else:
                    resource = await InstructorAssignmentService(session, user, event.assignment) \
                        .get_instructor_assignment_schema()

            elif event.resource_type == ResourceType.USER:
                if event.user_type == UserType.STUDENT:
                    resource = await StudentSchema.from_orm(event.user)
                elif event.user_type == UserType.INSTRUCTOR:
                    resource = await InstructorSchema.from_orm(event.user)
                else:
                    continue

                if user.user_type == UserType.STUDENT:
                    # Users should only see instructor changes
                    if event.user_type != UserType.INSTRUCTOR: continue

            elif event.resource_type == ResourceType.SUBMISSION:
                resource = SubmissionSchema.from_orm(event.submission)

            else:
                raise NotImplementedError("Unrecognized CRUD event resource type: ", event.resource_type.value)
            
            await websocket_service.send_message_to_user(user, WebsocketCrudMessage(
                operation_type=event.crud_type,
                resource_type=event.resource_type,
                resource=resource
            ))