from .base import CustomException

class LDAPConnectionTimeoutException(CustomException):
    code = 500
    error_code = "LDAP__CONNECTION_TIMEOUT"
    message = "ldap connection timed out, try again shortly"