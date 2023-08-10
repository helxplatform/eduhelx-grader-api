from app.schemas import RefreshTokenSchema
from core.exceptions.token import DecodeTokenException
from core.utils.token_helper import TokenHelper


class JwtService:
    async def verify_token(self, token: str) -> None:
        TokenHelper.decode(token=token)

    async def create_refresh_token(
        self,
        access_token: str,
        refresh_token: str,
    ) -> RefreshTokenSchema:
        access_token = TokenHelper.decode(token=access_token)
        refresh_token = TokenHelper.decode(token=refresh_token)
        if refresh_token.get("sub") != "refresh":
            raise DecodeTokenException()

        return RefreshTokenSchema(
            access_token=TokenHelper.encode(payload=access_token),
            refresh_token=TokenHelper.encode(payload={"sub": "refresh"}),
        )