import asyncio
from typing import BinaryIO
from sqlalchemy.orm import Session
from app.core.config import settings
from app.services.canvas_service import CanvasService, UpdateCanvasAssignmentBody
from app.services.course_service import CourseService
from app.services.ldap_service import LDAPService
from app.services.assignment_service import AssignmentService
from app.services.user.student_service import StudentService
from app.services.user.instructor_service import InstructorService
from app.models import AssignmentModel, SubmissionModel
from app.schemas.course import UpdateCourseSchema
from app.schemas.assignment import UpdateAssignmentSchema
from app.core.exceptions import (
    AssignmentNotFoundException, NoCourseExistsException, 
    UserNotFoundException, LMSUserNotFoundException
)

class LmsSyncService:
    def __init__(self, session: Session):
        self.canvas_service = CanvasService(session)
        self.course_service = CourseService(session)
        self.assignment_service = AssignmentService(session)
        self.student_service = StudentService(session)
        self.instructor_service = InstructorService(session)
        self.ldap_service = LDAPService()
        self.session = session

    async def get_assignment(self, assignment_id):
        return await self.canvas_service.get_assignment(assignment_id)

    async def sync_course(self):
        print("SYNC COURSE")
        try:
            canvas_course = await self.canvas_service.get_course()
            print("CANVAS COURSE EXISTS")

            # Check if a course already exists in the database
            if(await self.course_service.get_course()):
                print("COURSE EXISTS ALREADY")
                #update the existing course
                await self.course_service.update_course(UpdateCourseSchema(
                    name=canvas_course["name"]
                ))
                print("UPDATED COURSE")

        except NoCourseExistsException as e:
            print("CREATING COURSE (LMS)", e)
            return await CourseService(self.session).create_course(name=canvas_course['name'])


    async def sync_assignments(self):
        canvas_assignments = await self.canvas_service.get_assignments()
        db_assignments = await self.assignment_service.get_assignments()

        # Delete assignments that are in the database but not in Canvas
        for assignment in db_assignments:
            if assignment.id not in [a['id'] for a in canvas_assignments]:
                await self.assignment_service.delete_assignment(assignment)

        for assignment in canvas_assignments:
            # Canvas uses -1 for unlimited attempts.
            max_attempts = assignment["allowed_attempts"] if assignment["allowed_attempts"] >= 0 else None
            try:
                db_assignment = await self.assignment_service.get_assignment_by_id(assignment['id'])

                await self.assignment_service.update_assignment(db_assignment, UpdateAssignmentSchema(
                    name=assignment["name"],
                    available_date=assignment["unlock_at"],
                    due_date=assignment["due_at"],
                    is_published=assignment["published"],
                    max_attempts=max_attempts
                ))

            except AssignmentNotFoundException as e:
                #create a new assignment
                await self.assignment_service.create_assignment(
                    id=assignment['id'],
                    name=assignment['name'], 
                    due_date=assignment['due_at'], 
                    available_date=assignment['unlock_at'],
                    directory_path=assignment['name'],
                    is_published=assignment['published'],
                    max_attempts=max_attempts
                )
        
        return canvas_assignments

    async def sync_students(self):
        db_students = await self.student_service.list_students()
        canvas_students = await self.canvas_service.get_students()

        # If this course runs on a 2U Digital Campus instance, remove ":UNC" from the PID
        for student in canvas_students:
            sis_user_id = student.get("sis_user_id")
            if sis_user_id and ':' in sis_user_id:
                student["sis_user_id"] = sis_user_id.split(':')[0]

        canvas_student_pids = [s["sis_user_id"] for s in canvas_students]
        
        # Delete students that are in the database but not in Canvas
        for student in db_students:
            print("getting student pid", student.onyen)
            student_pid = await self.canvas_service.get_pid_from_onyen(student.onyen)
            print("student pid is", student_pid)
            if student_pid not in canvas_student_pids:
                await self.student_service.delete_user(student.onyen)
                try: await self.canvas_service.unassociate_pid_from_user(student.onyen)
                except LMSUserNotFoundException: pass
       
        for student in canvas_students:
            pid, email, name = student.get("sis_user_id"), student.get("email"), student.get("name")
            if pid is None or email is None or name is None:
                print("Skipping over pending student", name or "<unknown>")
                continue

            try:
                print("getting user info for ", pid)
                user_info = self.ldap_service.get_user_info(pid)
                print(pid, "->", user_info.onyen)
            except:
                print("Skipping over student not in LDAP: ", pid or "<unknown>")
                continue

            try:
                await self.student_service.get_user_by_onyen(user_info.onyen)

            except UserNotFoundException:
                #create a new student
                print("student doesn't exist", user_info.onyen)
                await self.student_service.create_student(
                    onyen=user_info.onyen,
                    name=name,
                    email=email
                )
                print("associate pid", pid, "to onyen", user_info.onyen)
                await self.canvas_service.associate_pid_to_user(user_info.onyen, pid)

        return canvas_students
    
    async def sync_instructors(self):
        db_instructors = await self.instructor_service.list_instructors()
        canvas_instructors = await self.canvas_service.get_instructors()

        # If this course runs on a 2U Digital Campus instance, remove ":UNC" from the PID
        for instructor in canvas_instructors:
            sis_user_id = instructor.get("sis_user_id")
            if sis_user_id and ':' in sis_user_id:
                instructor["sis_user_id"] = sis_user_id.split(':')[0]

        canvas_instructor_pids = [i["sis_user_id"] for i in canvas_instructors]
       
        # Delete instructors that are in the database but not in Canvas
        for instructor in db_instructors:
            print("getting instructor pid", instructor.onyen)
            instructor_pid = await self.canvas_service.get_pid_from_onyen(instructor.onyen)
            print("instructor pid is", instructor_pid)
            if instructor_pid not in canvas_instructor_pids:
                await self.instructor_service.delete_user(instructor.onyen)
                try: await self.canvas_service.unassociate_pid_from_user(instructor.onyen)
                except LMSUserNotFoundException: pass
        
        for instructor in canvas_instructors:
            pid, email, name = instructor.get("sis_user_id"), instructor.get("email"), instructor.get("name")
            if pid is None or email is None or name is None:
                print("Skipping over pending instructor", name or "<unknown>")
                continue

            print("getting user info for ", pid)
            user_info = self.ldap_service.get_user_info(pid)
            print(pid, "->", user_info.onyen)

            try:
                await self.instructor_service.get_user_by_onyen(user_info.onyen)

            except UserNotFoundException:
                #create a new instructor
                print("instructor doesn't exit", user_info.onyen)
                await self.instructor_service.create_instructor(
                    onyen=user_info.onyen,
                    name=name,
                    email=email
                )
                print("associate pid", pid, "to onyen", user_info.onyen)
                await self.canvas_service.associate_pid_to_user(user_info.onyen, pid)

        return canvas_instructors

    async def upsync_grade(
        self,
        submission: SubmissionModel,
        grade_percent: float,
        student_notebook: BinaryIO,
        comments: str | None = None,
    ):
        user_pid = await self.canvas_service.get_pid_from_onyen(submission.student.onyen)
        
        # If this course runs on a 2U Digital Campus instance, append ":UNC" to the PID
        if "digitalcampus" in settings.CANVAS_API_URL:
            user_pid += ":UNC"

        student = await self.canvas_service.get_student_by_pid(user_pid)
        await self.canvas_service.upload_grade(
            assignment_id=submission.assignment.id,
            user_id=student["id"],
            grade_percent=grade_percent,
            student_notebook=student_notebook,
            comments=comments
        )
            
    async def upsync_assignment(
        self,
        assignment: AssignmentModel
    ):
        await self.canvas_service.update_assignment(assignment.id, UpdateCanvasAssignmentBody(
            name=assignment.name,
            available_date=assignment.available_date,
            due_date=assignment.due_date,
            is_published=assignment.is_published,
            max_attempts=assignment.max_attempts
        ))
        

    async def downsync(self):
        print("Syncing the LMS with the database")
        await self.sync_course()
        await self.sync_assignments()
        await self.sync_students()
        await self.sync_instructors()
        print("Syncing complete")