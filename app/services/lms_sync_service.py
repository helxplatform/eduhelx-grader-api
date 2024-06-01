from datetime import datetime, timedelta
import json
from fastapi import Depends, HTTPException
import requests
import pandas as pd
import io, re
import asyncio
from app.core.config import settings
from app.services.canvas_service import CanvasService
from app.services.course_service import CourseService
from app.services.ldap_service import LDAPService
from app.services.assignment_service import AssignmentService
from app.services.user.student_service import StudentService
from app.services.user.instructor_service import InstructorService
from sqlalchemy.orm import Session
from app.core.exceptions import (
    AssignmentNotFoundException, NoCourseExistsException, 
    UserNotFoundException
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
            canvas_course = await self.canvas_service.get_course({"include[]": "total_students"})

            # Remove this after deciding what to do about null start/end dates
            if canvas_course['start_at'] is None:
                canvas_course['start_at'] = datetime(2000, 1, 1)
            if canvas_course['end_at'] is None:
                canvas_course['end_at'] = datetime.now() + timedelta(days=365*100)

            # Check if a course already exists in the database
            if(await self.course_service.get_course()):
                #update the existing course
                return await self.course_service.update_course(
                    name=canvas_course['name'], 
                    start_at=canvas_course['start_at'], 
                    end_at=canvas_course['end_at']
                )

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
                await self.assignment_service.delete_assignment(assignment.id)

        for assignment in canvas_assignments:
            try:
                db_assignment = await self.assignment_service.get_assignment_by_id(assignment['id'])
                
                #update the existing assignment
                await self.assignment_service.update_assignment_name(
                    assignment=db_assignment, 
                    new_name=assignment['name']
                )

                await self.assignment_service.update_assignment_available_date(
                    assignment=db_assignment,
                    available_date=assignment['unlock_at']
                )

                await self.assignment_service.update_assignment_due_date(
                    assignment=db_assignment,
                    due_date=assignment['due_at']
                )

            except AssignmentNotFoundException as e:
                #create a new assignment
                await self.assignment_service.create_assignment(
                    id=assignment['id'],
                    name=assignment['name'], 
                    due_date=assignment['due_at'], 
                    available_date=assignment['unlock_at'],
                    directory_path=assignment['name']
                )
        
        return canvas_assignments

    async def sync_students(self):
        canvas_students = await self.canvas_service.get_users({
            "enrollment_type": "student"
        })
        db_students = await self.student_service.list_students()
        
        if(db_students is not None):
            # Delete students that are in the database but not in Canvas
            for student in db_students:
                student_pid = await self.canvas_service.get_pid_from_onyen(student.onyen)
                if student_pid not in [s['sis_user_id'] for s in canvas_students]:
                    await self.canvas_service.unassociate_pid_from_user(student.onyen)
                    await self.student_service.delete_user(student.onyen)
       
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
        canvas_instructors = await self.canvas_service.get_users({
            "enrollment_type": "teacher"
        })
        db_instructors = await self.instructor_service.list_instructors()
       
        if(db_instructors is not None):       
            # Delete instructors that are in the database but not in Canvas
            for instructor in db_instructors:
                instructor_pid = await self.canvas_service.get_pid_from_onyen(instructor.onyen)
                if instructor_pid not in [i['sis_user_id'] for i in canvas_instructors]:
                    await self.canvas_service.unassociate_pid_from_user(instructor.onyen)
                    await self.instructor_service.delete_user(instructor.onyen)
        
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

    async def upload_grades_from_csv(self, grade_csv):
        df = pd.read_csv(io.StringIO(grade_csv.decode("utf-8")))
        
        for index, row in df.iterrows():
            try:
                assignment_id = self._extract_id(row['file'])
                user_pid = await self.canvas_service.get_pid_from_onyen(row['onyen'])
                students = await self.canvas_service.get_users({
                    "enrollment_type": "student"
                })
                student = next((student for student in students if student['sis_user_id'] == user_pid), None)

                await self.canvas_service.upload_grades(assignment_id, student["id"], row['percent_correct'])

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
            
        return {
            "message": "Successfully uploaded grades"
        }

    async def upsync_assignment(self, assignment):
        unlock_date = assignment.available_date.strftime("%Y-%m-%dT%H:%M:%S")
        due_date = assignment.due_date.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            await self.canvas_service.update_assignment(assignment.id,
            {
                "assignment": {
                    "unlock_at": unlock_date,
                    "due_at": due_date
                }
            })
        
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        
        return {
            "message": "Successfully updated assignment"
        }


    async def downsync(self):
        await asyncio.gather(
            self.sync_course(),
            self.sync_assignments(),
            self.sync_students(),
            self.sync_instructors()
        )

        return {
            "message": "Successfully synced the LMS with the database"
        }
    
    def _extract_id(self, filename: str):
        pattern = r"_(\d+)/"
        match = re.search(pattern, filename)
        
        # Check if a match is found
        if match:
            # Extract the first captured group (the digits)
            extracted_id = match.group(1)
            return extracted_id
        else:
            return None

# Delete below before merge
# 
# if True:
# #     # Currently only for testing purposes: a script that can be run to sync the LMS with the database
#     from app.database import SessionLocal

#     sess = SessionLocal()
#     lms = LmsSyncService(sess)
#     # asyncio.run(lms.sync_course())
#     # asyncio.run(lms.sync_students())
#     # asyncio.run(lms.sync_assignments())
#     asyncio.run(lms.downsync())

#     sess.close()