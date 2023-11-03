import ldap3
from ldap3.core.exceptions import LDAPSocketOpenError
from pydantic import BaseModel
from app.core.config import settings
from app.core.exceptions import LDAPConnectionTimeoutException, UserNotFoundException

class LDAPUserInfoSchema(BaseModel):
    onyen: str
    first_name: str
    last_name: str
    email: str

class LDAPService:
    def get_user_info(self, pid: str) -> LDAPUserInfoSchema:
        base_dn = "dc=unc,dc=edu"
        server = ldap3.Server(
            host=settings.LDAP_HOST,
            port=settings.LDAP_PORT,
            get_info=ldap3.ALL,
            use_ssl=settings.LDAP_PORT == 636,
            connect_timeout=settings.LDAP_TIMEOUT_SECONDS
        )
        try:
            with ldap3.Connection(
                server,
                user=settings.LDAP_SERVICE_ACCOUNT_BIND_DN,
                password=settings.LDAP_SERVICE_ACCOUNT_PASSWORD,
                auto_bind=True,
                receive_timeout=settings.LDAP_TIMEOUT_SECONDS
            ) as conn:
                search_filter = f"(&(objectClass=uncperson)(pid={pid}))"
                conn.search(
                    search_base=base_dn,
                    search_filter=search_filter,
                    search_scope=ldap3.SUBTREE,
                    attributes=[
                        "uid", # onyen
                        "givenName", # first name
                        "sn", # surname
                        "mail" # email
                    ]
                )
                if len(conn.entries) == 0:
                    raise UserNotFoundException()
                student = conn.entries[0]
                return LDAPUserInfoSchema(
                    onyen=student.uid.value,
                    first_name=student.givenName.value,
                    last_name=student.sn.value,
                    email=student.mail.value
                )
        except LDAPSocketOpenError as e:
            raise LDAPConnectionTimeoutException()