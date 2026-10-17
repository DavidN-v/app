"""Seguridad: contraseñas, tokens de sesión y control de acceso por roles."""

import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

_ITERATIONS = 240_000
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

ROLE_LEVEL = {"viewer": 0, "operator": 1, "approver": 2, "admin": 3}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(candidate.hex(), digest)


def create_token(user: User) -> str:
    settings = get_settings()
    payload = {
        "sub": user.username,
        "role": user.role,
        "exp": datetime.now(UTC) + timedelta(minutes=settings.jwt_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])


def current_user(token: str | None = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas", {"WWW-Authenticate": "Bearer"}
    )
    if not token:
        raise unauthorized
    try:
        username = decode_token(token)["sub"]
    except jwt.PyJWTError:
        raise unauthorized from None
    user = db.query(User).filter_by(username=username).one_or_none()
    if user is None:
        raise unauthorized
    return user


def require_role(minimum: str):
    def checker(user: User = Depends(current_user)) -> User:
        if ROLE_LEVEL[user.role] < ROLE_LEVEL[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Se requiere rol '{minimum}'")
        return user

    return checker
