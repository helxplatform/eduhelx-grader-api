from .base import CustomException

class MultipleCoursesExistException(CustomException):
    code = 500
    error_code = "COURSE__MULTIPLE_COURSES_EXIST"
    message = "database misconfigured, multiple courses exist in course table"

class NoCourseExistsException(CustomException):
    code = 500
    error_code = "COURSE__NO_COURSE_EXISTS"
    message = "database misconfigured, no course exists in course table"

class CourseAlreadyExistsException(CustomException):
    code = 409
    error_code = "COURSE__ALREADY_EXISTS"
    message = "course already exists, try modifying the existing course instead"

class CourseEndsBeforeStartDateException(CustomException):
    code = 400
    error_code = "COURSE__ENDS_BEFORE_START"
    message = "course cannot end before it has started"