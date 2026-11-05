import base64
import hashlib
import hmac
from typing import Annotated

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Header, HTTPException, status

from app.config import get_settings


class SecretCipher:
    def __init__(self, passphrase: str) -> None:
        digest = hashlib.sha256(passphrase.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError("认证密钥无法解密，请检查 SECRET_ENCRYPTION_KEY") from exc


settings = get_settings()
secret_cipher = SecretCipher(settings.secret_encryption_key)


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def require_admin(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    token = _bearer_token(authorization)
    if token is None or not hmac.compare_digest(token, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理端认证失败",
            headers={"WWW-Authenticate": "Bearer"},
        )


def is_valid_mcp_authorization(authorization: str | None) -> bool:
    token = _bearer_token(authorization)
    return token is not None and hmac.compare_digest(token, settings.mcp_api_key)

