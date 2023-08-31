from .base import CustomException

class MultipleCoursesExistException(CustomException):
    code = 500
    error_code = "COURSE__MULTIPLE_COURSES_EXIST"
    message = "database misconfigured, multiple courses exist in course table"

class NoCourseExistsException(CustomException):
    code = 500
    error_code = "COURSE__NO_COURSE_EXISTS"
    message = "database misconfigured, no course exists in course table"