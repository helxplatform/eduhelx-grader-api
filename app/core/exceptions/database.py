from sqlalchemy.exc import (
    SQLAlchemyError, IntegrityError, OperationalError, DataError
)
from .base import CustomException

# General exception for transactional errors
class DatabaseTransactionException(CustomException):
    code = 500
    error_code = "DATABASE__TRANSACTION_EXCEPTION"
    message = "failed to flush database transaction to server"

    def __init__(self, sqlalchemy_exc: SQLAlchemyError, message: str | None = None):
        super().__init__(message)
        self.sqlalchemy_exc = sqlalchemy_exc

    @classmethod
    def from_exception(cls, exc: SQLAlchemyError):
        orig = getattr(exc, "orig", None)
        message = str(orig) if orig is not None else None

        if isinstance(exc, IntegrityError):
            raise DatabaseIntegrityException(exc, message) from exc
        elif isinstance(exc, OperationalError):
            raise DatabaseOperationalException(exc, message) from exc
        elif isinstance(exc, DataError):
            raise DatabaseDataException(exc, message) from exc
        
        raise cls(exc, message) from exc

    @classmethod
    def raise_exception(cls, exc: SQLAlchemyError):
        raise cls.from_exception(exc)

# Relational integrity errors, e.g., unique violations, null violations, foreign key violations, etc.
class DatabaseIntegrityException(DatabaseTransactionException):
    code = 400
    error_code = "DATABASE__INTEGRITY_EXCEPTION"
    message = "database integrity violation encountered while flushing transaction"

# E.g. internal database errors, connection issues, timeouts, etc.
class DatabaseOperationalException(DatabaseTransactionException):
    code = 500
    error_code = "DATABASE__OPERATIONAL_EXCEPTION"
    message = "database operational error encountered while flushing transaction"

# E.g. string violates length restraint, type violations, division by 0, etc.
class DatabaseDataException(DatabaseTransactionException):
    code = 400
    error_code = "DATABASE__DATA_EXCEPTION"
    message = "database data violation encountered while flushing transaction"