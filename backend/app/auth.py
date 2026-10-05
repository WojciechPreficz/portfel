import asyncio
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from math import ceil

import bcrypt
from argon2 import PasswordHasher, extract_parameters
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel

from app.config import (
    PORTFEL_AUTH_DISABLED,
    PORTFEL_COOKIE_SECURE,
    PORTFEL_PASSWORD_HASH,
    PORTFEL_SECRET_KEY,
    PORTFEL_SESSION_HOURS,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_COOKIE_NAME = "portfel_session"
_SESSION_SALT = "portfel-session-v1"
_LOGIN_ATTEMPT_LIMIT = 5
_LOGIN_BLOCK_SECONDS = 15 * 60
_FAILED_LOGIN_DELAY_SECONDS = 0.3
_BCRYPT_HASH_PATTERN = re.compile(
    r"\$2[aby]\$(?:0[4-9]|[12]\d|3[01])\$[./A-Za-z0-9]{53}\Z"
)
_password_hasher = PasswordHasher()


@dataclass
class _LoginAttempts:
    failures: int = 0
    blocked_until: float = 0.0
    window_started: float = field(default_factory=time.monotonic)


_login_attempts: dict[str, _LoginAttempts] = {}
_login_attempts_lock = threading.Lock()


class LoginRequest(BaseModel):
    password: str


def validate_auth_configuration() -> None:
    if PORTFEL_AUTH_DISABLED:
        return
    if not PORTFEL_PASSWORD_HASH:
        raise RuntimeError(
            "Authentication is enabled, but PORTFEL_PASSWORD_HASH is not set. "
            "Set it to an Argon2 or bcrypt password hash, or set "
            "PORTFEL_AUTH_DISABLED=true for local development only."
        )
    if not PORTFEL_SECRET_KEY:
        raise RuntimeError(
            "Authentication is enabled, but PORTFEL_SECRET_KEY is not set. "
            "Generate a random key before starting the application."
        )
    if len(PORTFEL_SECRET_KEY.encode("utf-8")) < 32:
        raise RuntimeError("PORTFEL_SECRET_KEY must be at least 32 bytes long.")

    if PORTFEL_PASSWORD_HASH.startswith("$argon2"):
        try:
            extract_parameters(PORTFEL_PASSWORD_HASH)
        except (InvalidHashError, ValueError) as exc:
            raise RuntimeError("PORTFEL_PASSWORD_HASH is not a valid Argon2 hash.") from exc
    elif not _BCRYPT_HASH_PATTERN.fullmatch(PORTFEL_PASSWORD_HASH):
        raise RuntimeError(
            "PORTFEL_PASSWORD_HASH must be a valid Argon2 or bcrypt hash."
        )


def _serializer() -> URLSafeTimedSerializer:
    if PORTFEL_SECRET_KEY is None:
        raise RuntimeError("PORTFEL_SECRET_KEY is required when authentication is enabled.")
    return URLSafeTimedSerializer(PORTFEL_SECRET_KEY, salt=_SESSION_SALT)


def _verify_password(password: str) -> bool:
    if PORTFEL_PASSWORD_HASH is None:
        raise RuntimeError("PORTFEL_PASSWORD_HASH is required when authentication is enabled.")
    if PORTFEL_PASSWORD_HASH.startswith("$argon2"):
        try:
            return _password_hasher.verify(PORTFEL_PASSWORD_HASH, password)
        except VerifyMismatchError:
            return False
        except (InvalidHashError, VerificationError) as exc:
            raise RuntimeError("PORTFEL_PASSWORD_HASH could not be verified.") from exc
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            PORTFEL_PASSWORD_HASH.encode("ascii"),
        )
    except ValueError:
        return False


def _blocked_for(ip_address: str) -> int:
    now = time.monotonic()
    with _login_attempts_lock:
        attempts = _login_attempts.get(ip_address)
        if attempts is None:
            return 0
        if attempts.blocked_until > now:
            return ceil(attempts.blocked_until - now)
        if now - attempts.window_started >= _LOGIN_BLOCK_SECONDS:
            del _login_attempts[ip_address]
        return 0


def _record_failure(ip_address: str) -> None:
    now = time.monotonic()
    with _login_attempts_lock:
        expired = [
            address
            for address, attempts in _login_attempts.items()
            if now - attempts.window_started >= _LOGIN_BLOCK_SECONDS
        ]
        for address in expired:
            del _login_attempts[address]
        attempts = _login_attempts.setdefault(
            ip_address,
            _LoginAttempts(window_started=now),
        )
        attempts.failures += 1
        if attempts.failures >= _LOGIN_ATTEMPT_LIMIT:
            attempts.blocked_until = now + _LOGIN_BLOCK_SECONDS


def _clear_attempts(ip_address: str) -> None:
    with _login_attempts_lock:
        _login_attempts.pop(ip_address, None)


async def _delay_failed_login() -> None:
    await asyncio.sleep(_FAILED_LOGIN_DELAY_SECONDS)


def require_auth(request: Request) -> str:
    if PORTFEL_AUTH_DISABLED:
        return "user"

    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = _serializer().loads(
            token,
            max_age=PORTFEL_SESSION_HOURS * 60 * 60,
        )
    except BadSignature:
        raise HTTPException(status_code=401, detail="Not authenticated") from None

    subject = payload.get("sub") if isinstance(payload, dict) else None
    if not isinstance(subject, str) or not secrets.compare_digest(subject, "user"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return subject


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    if PORTFEL_AUTH_DISABLED:
        return {"authenticated": True}

    ip_address = request.client.host if request.client else "unknown"
    retry_after = _blocked_for(ip_address)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts",
            headers={"Retry-After": str(retry_after)},
        )

    if not await run_in_threadpool(_verify_password, payload.password):
        _record_failure(ip_address)
        await _delay_failed_login()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    _clear_attempts(ip_address)
    token = _serializer().dumps({"sub": "user"})
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        max_age=PORTFEL_SESSION_HOURS * 60 * 60,
        path="/",
        secure=PORTFEL_COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )
    return {"authenticated": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key=_COOKIE_NAME,
        path="/",
        secure=PORTFEL_COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )
    return {"authenticated": False}


@router.get("/me")
def me(_user: str = Depends(require_auth)):
    return {"authenticated": True}
