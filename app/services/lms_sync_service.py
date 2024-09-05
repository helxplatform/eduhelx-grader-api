import asyncio
from pydantic import BaseModel, root_validator
from typing import BinaryIO
from sqlalchemy.orm import Session
from app.core.config import settings
from app.services import CourseService, CanvasService, LDAPService, AssignmentService, StudentService, InstructorService, UserService, UpdateCanvasAssignmentBody, LDAPUserInfoSchema
from app.models import AssignmentModel, StudentModel, SubmissionModel, InstructorModel, UserModel
from app.schemas import UpdateCourseSchema, CreateAssignmentSchema, UpdateAssignmentSchema, CreateStudentSchema, CreateInstructorSchema
from app.core.exceptions import (
    AssignmentNotFoundException, NoCourseExistsException, 
    UserNotFoundException, LMSUserNotFoundException
)

class DatabaseLMSResourcePair(BaseModel):
    # User exists in LMS but not DB = create
    # User exists in DB but not LMS = delete
    # User exists in both DB and LMS = update
    db_resource: object | None
    lms_resource: dict | None

    # User info may not be provided on user deletion, since it isn't needed.
    user_info: LDAPUserInfoSchema | None

    @root_validator
    def check_resource_defined(cls, values):
        db_resource, lms_resource = values.get("db_resource"), values.get("lms_resource")
        if db_resource is None and lms_resource is None:
            raise ValueError('At least one of "db_resource", "lms_resource" must be non-null')
        return values
    
class DatabaseLMSResourceCreatePair(DatabaseLMSResourcePair):
    db_resource: None
    lms_resource: dict

class DatabaseLMSResourceUpdatePair(DatabaseLMSResourcePair):
    db_resource: object
    lms_resource: dict

class DatabaseLMSResourceDeletePair(DatabaseLMSResourcePair):
    db_resource: object
    lms_resource: None

class LmsSyncService:
    def __init__(self, session: Session):
        self.canvas_service = CanvasService(session)
        self.course_service = CourseService(session)
        self.assignment_service = AssignmentService(session)
        self.student_service = StudentService(session)
        self.instructor_service = InstructorService(session)
        self.user_service = UserService(session)
        self.ldap_service = LDAPService()
        self.session = session

    async def get_assignments(self): return await self.canvas_service.get_assignments()

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
                    name=canvas_course["name"],
                    start_at=canvas_course["start_at"],
                    end_at=canvas_course["end_at"]
                ))
                print("UPDATED COURSE")

        except NoCourseExistsException as e:
            print("CREATING COURSE (LMS)", e)
            return await CourseService(self.session).create_course(
                name=canvas_course['name'], 
                start_at=canvas_course['start_at'], 
                end_at=canvas_course['end_at']
            )
    
    async def _pair_db_canvas_users(
        self,
        db_users: list[UserModel],
        canvas_users: list[dict],
        canvas_user_pids: list[str]
    ) -> tuple[list[DatabaseLMSResourceCreatePair],list[DatabaseLMSResourceUpdatePair],list[DatabaseLMSResourceDeletePair]]:
        pairs = []
        print([u.onyen for u in db_users])
        print([u.get("name") for u in canvas_users])
        async def process_canvas_user(canvas_user) -> None:
            pid, email, name = canvas_user.get("sis_user_id"), canvas_user.get("email"), canvas_user.get("name")
            if pid is None or email is None or name is None:
                print("Skipping over pending user", name or email or "<unknown>")
                return

            try:
                print("getting user info for ", pid)
                user_info = self.ldap_service.get_user_info(pid)
                print(pid, "->", user_info.onyen)
            except UserNotFoundException:
                print("Skipping over student not in LDAP: ", pid or email or "<unknown>")
                return

            try:
                user = await self.user_service.get_user_by_onyen(user_info.onyen)
                pairs.append(DatabaseLMSResourcePair(db_resource=user, lms_resource=canvas_user, user_info=user_info))

            except UserNotFoundException:
                pairs.append(DatabaseLMSResourcePair(db_resource=None, lms_resource=canvas_user, user_info=user_info))
        

        # We begin by checking if there are any users that have been deleted from Canvas.
        # This is 1 DB call per user so doesn't really need optimization.
        for db_user in db_users:
            pid = await self.canvas_service.get_pid_from_onyen(db_user.onyen)
            if pid not in canvas_user_pids:
                pairs.append(DatabaseLMSResourcePair(db_resource=db_user, lms_resource=None))
        
        # Then we process Canvas users
        await asyncio.gather(*[process_canvas_user(u) for u in canvas_users])

        return self._group_resource_pairs_by_operation(pairs)
    
    async def _pair_db_canvas_assignments(
        self,
        db_assignments: list[AssignmentModel],
        canvas_assignments: list[dict]
    ) -> tuple[list[DatabaseLMSResourceCreatePair],list[DatabaseLMSResourceUpdatePair],list[DatabaseLMSResourceDeletePair]]:
        pairs = []

        canvas_assignment_ids = [a["id"] for a in canvas_assignments]
        for db_assignment in db_assignments:
            if db_assignment.id not in canvas_assignment_ids:
                pairs.append(DatabaseLMSResourcePair(db_resource=db_assignment, lms_resource=None))

        for canvas_assignment in canvas_assignments:
            try:
                db_assignment = await self.assignment_service.get_assignment_by_id(canvas_assignment["id"])
                pairs.append(DatabaseLMSResourcePair(db_resource=db_assignment, lms_resource=canvas_assignment))

            except AssignmentNotFoundException as e:
                pairs.append(DatabaseLMSResourcePair(db_resource=None, lms_resource=canvas_assignment))

        return self._group_resource_pairs_by_operation(pairs)

    async def _create_students_from_pairs(self, pairs: list[DatabaseLMSResourceCreatePair]):
        if len(pairs) == 0: return

        tuple_resource_pairs = [(pair.db_resource, pair.lms_resource, pair.user_info) for pair in pairs]
        await self.student_service.create_students([
            CreateStudentSchema(
                onyen=user_info.onyen,
                name=canvas_student["name"],
                email=canvas_student["email"]
            )
            for (db_student, canvas_student, user_info) in tuple_resource_pairs
        ])
        for pair in pairs:
            print("ASSOCIATE STUDENT", pair.user_info.onyen)
            await self.canvas_service.associate_pid_to_user(pair.user_info.onyen, pair.user_info.pid)

    async def _update_students_from_pairs(self, pairs: list[DatabaseLMSResourceUpdatePair]):
        if len(pairs) == 0: return
        
        # Not implemented.
        pass

    async def _delete_students_from_pairs(self, pairs: list[DatabaseLMSResourceDeletePair]):
        if len(pairs) == 0: return

        db_students = [pair.db_resource for pair in pairs]
        
        # We don't have a batch user deletion method at the moment due to cleanup concerns.
        await asyncio.gather(*[
            self.student_service.delete_user(db_student)
            for db_student in db_students
        ])
            
    async def sync_students(self):
        db_students = await self.student_service.list_students()
        canvas_students = await self.canvas_service.get_students()

        # If this course runs on a 2U Digital Campus instance, remove ":UNC" from the PID
        for student in canvas_students:
            sis_user_id = student.get("sis_user_id")
            if sis_user_id and ':' in sis_user_id:
                student["sis_user_id"] = sis_user_id.split(':')[0]

        canvas_student_pids = [s["sis_user_id"] for s in canvas_students]
        
        (create_pairs, update_pairs, delete_pairs) = await self._pair_db_canvas_users(
            db_students,
            canvas_students,
            canvas_student_pids
        )
        await asyncio.gather(
            self._create_students_from_pairs(create_pairs),
            self._update_students_from_pairs(update_pairs),
            self._delete_students_from_pairs(delete_pairs)   
        )

    async def _create_instructors_from_pairs(self, pairs: list[DatabaseLMSResourceCreatePair]):
        if len(pairs) == 0: return
        
        tuple_resource_pairs = [(pair.db_resource, pair.lms_resource, pair.user_info) for pair in pairs]
        await self.instructor_service.create_instructors([
            CreateInstructorSchema(
                onyen=user_info.onyen,
                name=canvas_instructor["name"],
                email=canvas_instructor["email"]
            )
            for (db_instructor, canvas_instructor, user_info) in tuple_resource_pairs
        ])
        for pair in pairs:
            print("ASSOCIATE INSTRUCTOR", pair.user_info.onyen)
            await self.canvas_service.associate_pid_to_user(pair.user_info.onyen, pair.user_info.pid)

    async def _update_instructors_from_pairs(self, pairs: list[DatabaseLMSResourceUpdatePair]):
        if len(pairs) == 0: return

        # Not implemented.
        pass

    async def _delete_instructors_from_pairs(self, pairs: list[DatabaseLMSResourceDeletePair]):
        if len(pairs) == 0: return

        db_instructors = [pair.db_resource for pair in pairs]
        
        # We don't have a batch user deletion method at the moment due to cleanup concerns.
        await asyncio.gather(*[
            self.instructor_service.delete_user(db_instructor)
            for db_instructor in db_instructors
        ])

    async def sync_instructors(self):
        db_instructors = await self.instructor_service.list_instructors()
        canvas_instructors = await self.canvas_service.get_instructors()

        # If this course runs on a 2U Digital Campus instance, remove ":UNC" from the PID
        for instructor in canvas_instructors:
            sis_user_id = instructor.get("sis_user_id")
            if sis_user_id and ':' in sis_user_id:
                instructor["sis_user_id"] = sis_user_id.split(':')[0]

        canvas_instructor_pids = [i["sis_user_id"] for i in canvas_instructors]
        
        (create_pairs, update_pairs, delete_pairs) = await self._pair_db_canvas_users(
            db_instructors,
            canvas_instructors,
            canvas_instructor_pids
        )
        await asyncio.gather(
            self._create_instructors_from_pairs(create_pairs),
            self._update_instructors_from_pairs(update_pairs),
            self._delete_instructors_from_pairs(delete_pairs)   
        )

    async def _create_assignments_from_pairs(self, pairs: list[DatabaseLMSResourceCreatePair]):
        if len(pairs) == 0: return

        canvas_assignments = [pair.lms_resource for pair in pairs]
        await self.assignment_service.create_assignments([
            CreateAssignmentSchema(
                id=canvas_assignment["id"],
                name=canvas_assignment["name"], 
                due_date=canvas_assignment["due_at"], 
                available_date=canvas_assignment["unlock_at"],
                directory_path=canvas_assignment["name"],
                is_published=canvas_assignment["published"],
                max_attempts=canvas_assignment.get("allowed_attempts") if canvas_assignment.get("allowed_attempts", -1) >= 0 else None
            )
            for canvas_assignment in canvas_assignments
        ])

    async def _update_assignments_from_pairs(self, pairs: list[DatabaseLMSResourceUpdatePair]):
        if len(pairs) == 0: return

        tuple_resource_pairs = [(pair.db_resource, pair.lms_resource) for pair in pairs]
        await self.assignment_service.update_assignments([
            (
                db_assignment,
                UpdateAssignmentSchema(
                    name=canvas_assignment["name"],
                    available_date=canvas_assignment["unlock_at"],
                    due_date=canvas_assignment["due_at"],
                    max_attempts=canvas_assignment.get("allowed_attempts") if canvas_assignment.get("allowed_attempts", -1) >= 0 else None
                )
            ) for (db_assignment, canvas_assignment) in tuple_resource_pairs
        ])

    async def _delete_assignments_from_pairs(self, pairs: list[DatabaseLMSResourceDeletePair]):
        if len(pairs) == 0: return

        db_assignments = [pair.db_resource for pair in pairs]
        await self.assignment_service.delete_assignments(db_assignments)
    
    async def sync_assignments(self):
        db_assignments = await self.assignment_service.get_assignments()
        canvas_assignments = await self.canvas_service.get_assignments()

        (create_pairs, update_pairs, delete_pairs) = await self._pair_db_canvas_assignments(db_assignments, canvas_assignments)
        await asyncio.gather(
            self._create_assignments_from_pairs(create_pairs),
            self._update_assignments_from_pairs(update_pairs),
            self._delete_assignments_from_pairs(delete_pairs)
        )
        

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
        await asyncio.gather(self.sync_students(), self.sync_instructors())
        print("Syncing complete")

    @staticmethod
    def _group_resource_pairs_by_operation(
        pairs: list[DatabaseLMSResourcePair]
    ) -> tuple[list[DatabaseLMSResourceCreatePair],list[DatabaseLMSResourceUpdatePair],list[DatabaseLMSResourceDeletePair]]:
        creates, updates, deletes = [], [], []
        for pair in pairs:
            if pair.db_resource is None and pair.lms_resource is not None:
                creates.append(pair)

            if pair.db_resource is not None and pair.lms_resource is not None:
                updates.append(pair)

            if pair.db_resource is not None and pair.lms_resource is None:
                deletes.append(pair)

        return (creates, updates, deletes)