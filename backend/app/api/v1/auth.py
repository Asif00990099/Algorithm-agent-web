"""Authentication: register, login (with optional 2FA), token refresh,
TOTP setup. Auth endpoints have their own tighter rate limit."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import rate_limit_check
from app.core.config import settings
from app.core.deps import client_ip, get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_totp_secret,
    hash_password,
    totp_provisioning_uri,
    verify_password,
    verify_totp,
)
from app.db.session import get_db
from app.models import AuditLog, User
from app.schemas.common import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    TwoFactorSetupResponse,
    TwoFactorVerifyRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _auth_rate_limit(request: Request) -> None:
    allowed = await rate_limit_check(f"auth:{client_ip(request)}",
                                     settings.AUTH_RATE_LIMIT_PER_MINUTE)
    if not allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Too many authentication attempts; try again shortly")


def _audit(db: AsyncSession, request: Request, action: str, user_id=None, detail=""):
    db.add(AuditLog(created_at=datetime.now(timezone.utc), user_id=user_id,
                    action=action, resource="auth", detail=detail,
                    ip_address=client_ip(request)))


@router.post("/register", response_model=UserOut, status_code=201,
             dependencies=[Depends(_auth_rate_limit)])
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    exists = await db.scalar(select(User).where(
        (User.email == body.email.lower()) | (User.username == body.username)))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or username already registered")
    user = User(email=body.email.lower(), username=body.username,
                hashed_password=hash_password(body.password),
                demo_balance=settings.DEMO_STARTING_BALANCE,
                demo_equity_high=settings.DEMO_STARTING_BALANCE)
    db.add(user)
    await db.flush()
    _audit(db, request, "user.register", user.id)
    await db.commit()
    return user


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(_auth_rate_limit)])
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.hashed_password):
        _audit(db, request, "auth.login_failed", detail=body.email)
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    if user.totp_enabled:
        if not body.totp_code or not verify_totp(user.totp_secret or "", body.totp_code):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Valid 2FA code required")
    user.last_login_at = datetime.now(timezone.utc)
    _audit(db, request, "auth.login", user.id)
    await db.commit()
    return TokenResponse(access_token=create_access_token(user.id, user.role.value),
                         refresh_token=create_refresh_token(user.id))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token, "refresh")
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    user = await db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive or not found")
    return TokenResponse(access_token=create_access_token(user.id, user.role.value),
                         refresh_token=create_refresh_token(user.id))


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
async def setup_2fa(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    secret = generate_totp_secret()
    user.totp_secret = secret
    user.totp_enabled = False
    await db.commit()
    return TwoFactorSetupResponse(secret=secret,
                                  provisioning_uri=totp_provisioning_uri(secret, user.email))


@router.post("/2fa/verify", response_model=UserOut)
async def verify_2fa(body: TwoFactorVerifyRequest, user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    if not user.totp_secret or not verify_totp(user.totp_secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid 2FA code")
    user.totp_enabled = True
    await db.commit()
    return user


@router.post("/2fa/disable", response_model=UserOut)
async def disable_2fa(body: TwoFactorVerifyRequest, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    if not user.totp_enabled or not verify_totp(user.totp_secret or "", body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid 2FA code")
    user.totp_enabled = False
    user.totp_secret = None
    await db.commit()
    return user
