"""Admin dashboard API: users, platform stats, audit logs, prompt templates,
runtime settings and server health."""
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_redis
from app.core.deps import require_admin
from app.db.session import get_db
from app.models import (AppSetting, Article, AuditLog, PromptTemplate, Signal,
                        Strategy, Trade, User, UserRole)
from app.schemas.common import AdminUserUpdateRequest, UserOut

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/stats")
async def platform_stats(db: AsyncSession = Depends(get_db)):
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    users_total = await db.scalar(select(func.count(User.id))) or 0
    trades_total = await db.scalar(select(func.count(Trade.id))) or 0
    trades_24h = await db.scalar(select(func.count(Trade.id)).where(Trade.created_at >= day_ago)) or 0
    signals_total = await db.scalar(select(func.count(Signal.id))) or 0
    signals_24h = await db.scalar(select(func.count(Signal.id)).where(Signal.created_at >= day_ago)) or 0
    articles_total = await db.scalar(select(func.count(Article.id))) or 0
    strategies_total = await db.scalar(select(func.count(Strategy.id))) or 0

    redis_ok = True
    try:
        await get_redis().ping()
    except Exception:  # noqa: BLE001
        redis_ok = False

    return {"users": users_total, "trades": trades_total, "trades_24h": trades_24h,
            "signals": signals_total, "signals_24h": signals_24h,
            "articles": articles_total, "strategies": strategies_total,
            "redis_healthy": redis_ok,
            "server_time": datetime.now(timezone.utc)}


@router.get("/users", response_model=list[UserOut])
async def list_users(q: str = Query("", max_length=64),
                     limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                     db: AsyncSession = Depends(get_db)):
    query = select(User)
    if q:
        query = query.where(User.email.ilike(f"%{q}%") | User.username.ilike(f"%{q}%"))
    return (await db.execute(query.order_by(User.created_at.desc())
                             .limit(limit).offset(offset))).scalars().all()


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: str, body: AdminUserUpdateRequest,
                      db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if body.role is not None:
        try:
            user.role = UserRole(body.role)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role") from exc
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.demo_balance is not None:
        user.demo_balance = body.demo_balance
    await db.commit()
    return user


@router.get("/audit-logs")
async def audit_logs(action: str = Query("", max_length=64),
                     limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
                     db: AsyncSession = Depends(get_db)):
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action.ilike(f"%{action}%"))
    rows = (await db.execute(q.order_by(AuditLog.created_at.desc())
                             .limit(limit).offset(offset))).scalars().all()
    return [{"id": r.id, "created_at": r.created_at, "user_id": r.user_id,
             "action": r.action, "resource": r.resource, "detail": r.detail,
             "ip_address": r.ip_address} for r in rows]


# ------------------------------------------------------------------ prompts

class PromptIn(BaseModel):
    key: str = Field(min_length=2, max_length=64)
    content: str = Field(min_length=1)
    description: str = ""
    is_active: bool = True


@router.get("/prompts")
async def list_prompts(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(PromptTemplate).order_by(PromptTemplate.key))).scalars().all()
    return [{"id": p.id, "key": p.key, "content": p.content,
             "description": p.description, "is_active": p.is_active} for p in rows]


@router.put("/prompts/{key}")
async def upsert_prompt(key: str, body: PromptIn, db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(PromptTemplate).where(PromptTemplate.key == key))
    if row is None:
        row = PromptTemplate(key=key, content=body.content,
                             description=body.description, is_active=body.is_active)
        db.add(row)
    else:
        row.content, row.description, row.is_active = body.content, body.description, body.is_active
    await db.commit()
    return {"key": key, "updated": True}


# ------------------------------------------------------------------ settings

class SettingIn(BaseModel):
    value: str


ALLOWED_SETTINGS = {
    "ai_provider", "signal_symbols", "news_auto_publish", "scanner_enabled",
    "signal_timeframes", "maintenance_mode", "live_trading_enabled",
}


@router.get("/settings")
async def get_settings_kv(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AppSetting))).scalars().all()
    return {r.key: r.value for r in rows}


@router.put("/settings/{key}")
async def set_setting(key: str, body: SettingIn, db: AsyncSession = Depends(get_db)):
    if key not in ALLOWED_SETTINGS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Unknown setting; allowed: {sorted(ALLOWED_SETTINGS)}")
    row = await db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=body.value)
        db.add(row)
    else:
        row.value = body.value
    await db.commit()
    return {key: body.value}
