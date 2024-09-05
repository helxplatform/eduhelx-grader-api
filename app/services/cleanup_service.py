from sqlalchemy.orm import Session
from app.models import UserModel, CourseModel, GradeReportModel, AssignmentModel
from app.services import GiteaService, KubernetesService
from app.core.exceptions import GiteaNotFoundException

class CleanupService:
    class Grading:
        def __init__(self, session: Session, grade_report: GradeReportModel):
            self.session = session
            self.grade_report = grade_report

        async def undo_grade_assignment(self, delete_database_grade_report=False):
            if delete_database_grade_report:
                self.session.delete(self.grade_report)
                self.session.commit()

    class Course:
        def __init__(self, session: Session, course: CourseModel):
            self.session = session
            self.course = course

        async def undo_create_course(self, delete_database_course=False, delete_gitea_organization=False):
            from app.services import CourseService

            gitea_service = GiteaService(self.session)

            if delete_database_course:
                self.session.delete(self.course)
                self.session.commit()
            
            if delete_gitea_organization:
                instructor_organization_name = CourseService._compute_instructor_gitea_organization_name(self.course.name)
                await gitea_service.delete_organization(instructor_organization_name, purge=True)

    class User:
        def __init__(self, session: Session, user: UserModel, autogen_password: str | None = None):
            self.session = session
            self.user = user
            self.autogen_password = autogen_password

        async def undo_create_user(self, delete_database_user=False, delete_password_secret=False, delete_gitea_user=False):
            from app.services import CourseService

            course = await CourseService(self.session).get_course()
            if delete_database_user:
                self.session.delete(self.user)
                self.session.commit()

            if delete_password_secret:
                KubernetesService().delete_credential_secret(course.name, self.user.onyen)
            
            if delete_gitea_user:
                await GiteaService(self.session).delete_user(self.user.onyen, purge=True)
            
        async def undo_delete_user(self, create_password_secret=False):
            from app.services import CourseService

            course = await CourseService(self.session).get_course()
            if create_password_secret:
                KubernetesService().create_credential_secret(
                    course_name=course.name,
                    onyen=self.user.onyen,
                    password=self.autogen_password,
                    user_type=self.user.user_type
                )

    class Assignment:
        def __init__(self, session: Session, assignments: list[AssignmentModel]):
            self.session = session
            self.assignments = assignments

        async def undo_create_assignments(self, delete_database_assignments=False):
            if delete_database_assignments:
                for assignment in self.assignments:
                    self.session.delete(assignment)
                self.session.commit()