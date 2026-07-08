"""Admin dashboard API: users, platform stats, audit logs, prompt templates,
runtime settings and server health."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_redis
from app.core.deps import require_admin
from app.db.session import get_db
from app.models import Article, AuditLog, PromptTemplate, Signal, Strategy, Trade, User, UserRole
from app.schemas.common import AdminUserUpdateRequest, UserOut
from app.services import app_settings, runtime_config

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


# ------------------------------------------------------------- API management

class ApiKeyIn(BaseModel):
    value: str = Field(min_length=1, max_length=512)


@router.get("/api-keys")
async def list_api_keys(db: AsyncSession = Depends(get_db)):
    """Status of every external API provider (values masked)."""
    return await runtime_config.list_status(db)


@router.put("/api-keys/{provider}")
async def set_api_key(provider: str, body: ApiKeyIn,
                      db: AsyncSession = Depends(get_db)):
    if provider not in runtime_config.PROVIDERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Unknown provider; allowed: {sorted(runtime_config.PROVIDERS)}")
    await runtime_config.set_credential(db, provider, body.value.strip())
    db.add(AuditLog(created_at=datetime.now(timezone.utc), action="admin.api_key.set",
                    resource=provider, detail="value updated"))
    await db.commit()
    return {"provider": provider, "configured": True,
            "masked": runtime_config.mask(body.value.strip())}


@router.delete("/api-keys/{provider}", status_code=204)
async def delete_api_key(provider: str, db: AsyncSession = Depends(get_db)):
    if provider not in runtime_config.PROVIDERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown provider")
    await runtime_config.delete_credential(db, provider)
    db.add(AuditLog(created_at=datetime.now(timezone.utc), action="admin.api_key.delete",
                    resource=provider))
    await db.commit()


# ------------------------------------------------------------------ settings


class SettingsBulkIn(BaseModel):
    values: dict[str, object]


@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db)):
    """Full settings schema (grouped) with current values for the admin UI."""
    return await app_settings.schema_with_values(db)


@router.put("/settings")
async def update_settings(body: SettingsBulkIn, db: AsyncSession = Depends(get_db)):
    """Bulk-update settings; unknown keys are ignored, invalid values rejected."""
    try:
        applied = await app_settings.set_many(db, body.values)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid setting value: {exc}") from exc
    db.add(AuditLog(created_at=datetime.now(timezone.utc), action="admin.settings.update",
                    resource="settings", detail=",".join(applied.keys())))
    await db.commit()
    return {"updated": applied}
