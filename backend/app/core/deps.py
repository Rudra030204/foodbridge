"""FastAPI dependencies: DB session, current user, role guards."""
from typing import Callable, Iterator

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import forbidden
from app.core.security import decode_token
from app.db.models import User
from app.db.session import SessionLocal, SessionRead

bearer = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Iterator[Session]:
    """GET requests are read-only by contract and use deferred transactions (see db/session.py)."""
    db = (SessionRead if request.method == "GET" else SessionLocal)()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated.", headers={"WWW-Authenticate": "Bearer"})
    payload = decode_token(creds.credentials, "access")
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token.", headers={"WWW-Authenticate": "Bearer"})
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account not found or suspended.")
    return user


def require_roles(*roles: str) -> Callable[[User], User]:
    """Dependency factory: only users with one of ``roles`` may proceed."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise forbidden(f"This action requires role: {', '.join(roles)}.")
        return user

    return _guard


require_admin = require_roles("admin")
require_donor = require_roles("donor")
require_ngo = require_roles("ngo")
require_volunteer = require_roles("volunteer")
