"""Seguridad: contraseñas, tokens de sesión y control de acceso por roles.

- Las contraseñas no se guardan en claro: se almacena un resumen PBKDF2-SHA256 con una sal
  aleatoria, de modo que dos usuarios con la misma contraseña tienen resúmenes distintos.
- Al iniciar sesión se entrega un token JWT firmado que el navegador envía en cada petición.
- Cada rol tiene un nivel; una ruta exige un nivel mínimo para poder usarse.
"""

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

# Número de iteraciones de PBKDF2: cuantas más, más costoso es probar contraseñas por fuerza bruta
_ITERATIONS = 240_000
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

# Jerarquía de roles: cada uno puede hacer lo mismo que los de nivel inferior
ROLE_LEVEL = {"viewer": 0, "operator": 1, "approver": 2, "admin": 3}


def hash_password(password: str) -> str:
    """Devuelve el texto que se guarda en la base de datos: algoritmo, iteraciones, sal y resumen."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Recalcula el resumen con la misma sal y lo compara en tiempo constante,
    para no dar pistas sobre la contraseña según lo que tarde la comparación."""
    try:
        _, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(candidate.hex(), digest)


def create_token(user: User) -> str:
    """Genera el token de sesión con el usuario, su rol y la fecha de caducidad."""
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
    """Obtiene el usuario a partir del token de la petición; responde 401 si no es válido."""
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
    """Crea una dependencia de FastAPI que solo deja pasar a usuarios con el rol indicado o superior."""
    def checker(user: User = Depends(current_user)) -> User:
        if ROLE_LEVEL[user.role] < ROLE_LEVEL[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Se requiere rol '{minimum}'")
        return user

    return checker
