"""Admin authentication service with JWT tokens."""
from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
import bcrypt

from app.core.config import settings
from app.core.errors import AuthenticationError
from app.core.logging import get_logger

logger = get_logger("admin_auth")

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(username: str) -> tuple[str, datetime]:
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.admin_jwt_expiry_hours)
    payload = {"sub": username, "exp": expires}
    token = jwt.encode(payload, settings.admin_jwt_secret, algorithm=ALGORITHM)
    return token, expires


def verify_token(token: str) -> str:
    """Verify JWT token and return username. Raises AuthenticationError on failure."""
    try:
        payload = jwt.decode(token, settings.admin_jwt_secret, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise AuthenticationError("Invalid token payload")
        return username
    except JWTError as e:
        raise AuthenticationError(f"Token verification failed: {e}")


# Simple in-memory admin store (seeded from env on startup)
_admin_users: dict[str, str] = {}  # username -> password_hash


def seed_admin_user() -> None:
    """Seed the initial admin user from environment variables."""
    global _admin_users
    if not _admin_users:
        _admin_users[settings.admin_username] = hash_password(settings.admin_password)
        logger.info("admin_user_seeded", username=settings.admin_username)


def authenticate_admin(username: str, password: str) -> str:
    """Authenticate admin and return JWT token."""
    seed_admin_user()
    stored_hash = _admin_users.get(username)
    if not stored_hash:
        raise AuthenticationError("Invalid credentials")
    if not verify_password(password, stored_hash):
        raise AuthenticationError("Invalid credentials")
    token, expires = create_access_token(username)
    logger.info("admin_login_success", username=username)
    return token
