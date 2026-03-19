from passlib.context import CryptContext

from app.db.models import get_setting, set_setting

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def admin_exists() -> bool:
    return bool(get_setting("admin_username")) and bool(get_setting("admin_password_hash"))


def create_admin(username: str, password: str) -> None:
    set_setting("admin_username", username.strip())
    set_setting("admin_password_hash", hash_password(password))


def verify_admin_credentials(username: str, password: str) -> bool:
    stored_username = get_setting("admin_username")
    stored_hash = get_setting("admin_password_hash")

    if not stored_username or not stored_hash:
        return False

    if username != stored_username:
        return False

    return verify_password(password, stored_hash)