import asyncio
from app.core.config import settings
from app.services.canvas_service import CanvasService, UpdateCanvasAssignmentBody
from app.services.course_service import CourseService
from app.services.ldap_service import LDAPService
from app.services.assignment_service import AssignmentService
from app.services.user.student_service import StudentService
from app.services.user.instructor_service import InstructorService
from app.models import AssignmentModel, StudentModel
from app.schemas.course import UpdateCourseSchema
from app.schemas.assignment import UpdateAssignmentSchema
from sqlalchemy.orm import Session
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

    async def sync_course(self):
        try:
            canvas_course = await self.canvas_service.get_course()

            # Check if a course already exists in the database
            if(await self.course_service.get_course()):
                #update the existing course
                await self.course_service.update_course(UpdateCourseSchema(
                    name=canvas_course["name"],
                    start_at=canvas_course["start_at"],
                    end_at=canvas_course["end_at"]
                ))

        except NoCourseExistsException as e:
            return await CourseService(self.session).create_course(
                name=canvas_course['name'], 
                start_at=canvas_course['start_at'], 
                end_at=canvas_course['end_at']
            )


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
                    max_attempts=max_attempts
                )
        
        return canvas_assignments

    async def sync_students(self):
        db_students = await self.student_service.list_students()
        canvas_students = await self.canvas_service.get_students()
        canvas_student_pids = [s["sis_user_id"] for s in canvas_students]
        
        if(db_students is not None):
            # Delete students that are in the database but not in Canvas
            for student in db_students:
                student_pid = await self.canvas_service.get_pid_from_onyen(student.onyen)
                if student_pid not in canvas_student_pids:
                    await self.student_service.delete_user(student.onyen)
                    try: await self.canvas_service.unassociate_pid_from_user(student.onyen)
                    except LMSUserNotFoundException: pass
       
        for student in canvas_students:
            pid = student['sis_user_id']
            user_info = self.ldap_service.get_user_info(pid)

            try:
                await self.student_service.get_user_by_onyen(user_info.onyen)

            except UserNotFoundException:
                #create a new student
                await self.student_service.create_student(
                    onyen=user_info.onyen,
                    name=student['name'],
                    email=student['email']
                )
                await self.canvas_service.associate_pid_to_user(user_info.onyen, pid)

        return canvas_students
    
    async def sync_instructors(self):
        db_instructors = await self.instructor_service.list_instructors()
        canvas_instructors = await self.canvas_service.get_instructors()
        canvas_instructor_pids = [i["sis_user_id"] for i in canvas_instructors]
       
        if(db_instructors is not None):       
            # Delete instructors that are in the database but not in Canvas
            for instructor in db_instructors:
                instructor_pid = await self.canvas_service.get_pid_from_onyen(instructor.onyen)
                if instructor_pid not in canvas_instructor_pids:
                    await self.instructor_service.delete_user(instructor.onyen)
                    try: await self.canvas_service.unassociate_pid_from_user(instructor.onyen)
                    except LMSUserNotFoundException: pass
        
        for instructor in canvas_instructors:
            pid = instructor['sis_user_id']
            user_info = self.ldap_service.get_user_info(pid)

            try:
                await self.instructor_service.get_user_by_onyen(user_info.onyen)

            except UserNotFoundException:
                #create a new instructor
                await self.instructor_service.create_instructor(
                    onyen=user_info.onyen,
                    name=instructor['name'],
                    email=instructor['email']
                )
                await self.canvas_service.associate_pid_to_user(user_info.onyen, pid)

        return canvas_instructors

    async def upload_grades(self, assignment_id: int, grades: list[dict]):
        for row in grades:
            user_pid = await self.canvas_service.get_pid_from_onyen(row['onyen'])
            student = await self.canvas_service.get_student_by_pid(user_pid)
            await self.canvas_service.upload_grade(assignment_id, student["id"], row['percent_correct'])
            
    async def upsync_assignment(self, assignment):
        await self.canvas_service.update_assignment(assignment.id, UpdateCanvasAssignmentBody(
            name=assignment.name,
            available_date=assignment.available_date,
            due_date=assignment.due_date
        ))

    async def get_current_submission_attempt(self, assignment: AssignmentModel, student: StudentModel):
        pid = await self.canvas_service.get_pid_from_onyen(student.onyen)
        student = await self.canvas_service.get_student_by_pid(pid)
        return await self.canvas_service.get_current_submission_attempt(assignment.id, student["id"])
        

    async def downsync(self):
        print("Syncing the LMS with the database")
        await self.sync_course()
        await self.sync_assignments()
        await self.sync_students()
        await self.sync_instructors()