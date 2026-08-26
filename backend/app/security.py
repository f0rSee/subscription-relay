from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Annotated

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import Settings

SESSION_COOKIE = "relay_admin_session"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


class SecretBox:
    def __init__(self, key_material: str):
        digest = hashlib.sha256(key_material.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Stored secret cannot be decrypted") from exc


@dataclass(frozen=True)
class AdminSession:
    username: str
    csrf_token: str


class SessionManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.serializer = URLSafeTimedSerializer(
            settings.session_secret, salt="subscription-relay-admin"
        )

    def authenticate(self, username: str, password: str) -> bool:
        if self.settings.admin_password is None:
            return False
        return secrets.compare_digest(username, self.settings.admin_username) and (
            secrets.compare_digest(password, self.settings.admin_password)
        )

    def create_cookie(self, username: str) -> tuple[str, AdminSession]:
        session = AdminSession(username=username, csrf_token=secrets.token_urlsafe(24))
        value = self.serializer.dumps(
            {"username": session.username, "csrf": session.csrf_token}
        )
        return value, session

    def read_cookie(self, value: str | None) -> AdminSession | None:
        if not value:
            return None
        try:
            payload = self.serializer.loads(value, max_age=SESSION_MAX_AGE_SECONDS)
        except (BadSignature, SignatureExpired):
            return None
        username = payload.get("username")
        csrf_token = payload.get("csrf")
        if not isinstance(username, str) or not isinstance(csrf_token, str):
            return None
        return AdminSession(username=username, csrf_token=csrf_token)


def require_admin(request: Request) -> AdminSession:
    manager: SessionManager = request.app.state.runtime.sessions
    session = manager.read_cookie(request.cookies.get(SESSION_COOKIE))
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(supplied, session.csrf_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token",
            )
    return session


AdminSessionDep = Annotated[AdminSession, Depends(require_admin)]
