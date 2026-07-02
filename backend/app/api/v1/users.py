"""User self-service: profile, watchlist, alerts, exchange API keys,
notifications and portfolio summary."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.security import encrypt_secret
from app.db.session import get_db
from app.models import (ExchangeApiKey, Notification, PriceAlert, Trade,
                        TradeStatus, User, WatchlistItem)
from app.schemas.common import (AlertIn, ApiKeyIn, UserOut, UserUpdateRequest,
                                WatchlistIn)
from app.services.market.binance import get_price

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(body: UserUpdateRequest, user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    if body.risk_per_trade_pct is not None:
        user.risk_per_trade_pct = body.risk_per_trade_pct
    if body.max_open_positions is not None:
        user.max_open_positions = body.max_open_positions
    await db.commit()
    return user


# ---------------------------------------------------------------- portfolio

@router.get("/me/portfolio")
async def portfolio(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    open_trades = (await db.execute(
        select(Trade).where(Trade.user_id == user.id, Trade.status == TradeStatus.OPEN))
    ).scalars().all()

    positions = []
    unrealized = 0.0
    exposure = 0.0
    for t in open_trades:
        price = await get_price(t.symbol)
        pnl = None
        if price is not None:
            direction = 1.0 if t.side == "long" else -1.0
            pnl = (price - t.entry_price) * t.quantity * direction
            unrealized += pnl
            exposure += price * t.quantity
        positions.append({
            "id": t.id, "symbol": t.symbol, "side": t.side, "mode": t.mode.value,
            "quantity": t.quantity, "entry_price": t.entry_price,
            "current_price": price, "unrealized_pnl": round(pnl, 4) if pnl is not None else None,
            "stop_loss": t.stop_loss, "take_profit": t.take_profit,
            "opened_at": t.opened_at,
        })

    closed_stats = (await db.execute(
        select(func.count(Trade.id),
               func.coalesce(func.sum(Trade.realized_pnl), 0.0),
               func.coalesce(func.sum(case((Trade.realized_pnl > 0, 1), else_=0)), 0))
        .where(Trade.user_id == user.id, Trade.status == TradeStatus.CLOSED))).one()
    total_closed, realized_pnl, wins = int(closed_stats[0]), float(closed_stats[1]), int(closed_stats[2])

    equity = user.demo_balance + unrealized + sum(
        (p["current_price"] or p["entry_price"]) * p["quantity"]
        for p in positions if p["side"] == "long" and p["mode"] == "demo")

    return {
        "demo_balance": round(user.demo_balance, 2),
        "equity": round(equity, 2),
        "unrealized_pnl": round(unrealized, 2),
        "realized_pnl": round(realized_pnl, 2),
        "open_positions": positions,
        "exposure": round(exposure, 2),
        "closed_trades": total_closed,
        "win_rate": round(wins / total_closed * 100, 2) if total_closed else 0.0,
    }


# ---------------------------------------------------------------- watchlist

@router.get("/me/watchlist")
async def get_watchlist(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items = (await db.execute(select(WatchlistItem).where(WatchlistItem.user_id == user.id)
                              .order_by(WatchlistItem.created_at))).scalars().all()
    return [{"id": i.id, "symbol": i.symbol, "asset_type": i.asset_type,
             "is_favorite": i.is_favorite} for i in items]


@router.post("/me/watchlist", status_code=201)
async def add_watchlist(body: WatchlistIn, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    item = WatchlistItem(user_id=user.id, symbol=body.symbol.upper(),
                         asset_type=body.asset_type, is_favorite=body.is_favorite)
    db.add(item)
    await db.commit()
    return {"id": item.id, "symbol": item.symbol}


@router.delete("/me/watchlist/{item_id}", status_code=204)
async def remove_watchlist(item_id: str, user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    await db.execute(delete(WatchlistItem).where(WatchlistItem.id == item_id,
                                                 WatchlistItem.user_id == user.id))
    await db.commit()


# ------------------------------------------------------------------- alerts

@router.get("/me/alerts")
async def get_alerts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    alerts = (await db.execute(select(PriceAlert).where(PriceAlert.user_id == user.id)
                               .order_by(PriceAlert.created_at.desc()))).scalars().all()
    return [{"id": a.id, "symbol": a.symbol, "condition": a.condition,
             "target_price": a.target_price, "is_triggered": a.is_triggered,
             "triggered_at": a.triggered_at} for a in alerts]


@router.post("/me/alerts", status_code=201)
async def add_alert(body: AlertIn, user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    alert = PriceAlert(user_id=user.id, symbol=body.symbol.upper(),
                       condition=body.condition, target_price=body.target_price)
    db.add(alert)
    await db.commit()
    return {"id": alert.id}


@router.delete("/me/alerts/{alert_id}", status_code=204)
async def delete_alert(alert_id: str, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    await db.execute(delete(PriceAlert).where(PriceAlert.id == alert_id,
                                              PriceAlert.user_id == user.id))
    await db.commit()


# ----------------------------------------------------------------- api keys

@router.get("/me/api-keys")
async def list_api_keys(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    keys = (await db.execute(select(ExchangeApiKey).where(ExchangeApiKey.user_id == user.id))
            ).scalars().all()
    # never return key material — labels and metadata only
    return [{"id": k.id, "exchange": k.exchange, "label": k.label,
             "is_testnet": k.is_testnet, "is_active": k.is_active,
             "created_at": k.created_at} for k in keys]


@router.post("/me/api-keys", status_code=201)
async def add_api_key(body: ApiKeyIn, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    key = ExchangeApiKey(user_id=user.id, exchange=body.exchange, label=body.label,
                         encrypted_key=encrypt_secret(body.api_key),
                         encrypted_secret=encrypt_secret(body.api_secret),
                         is_testnet=body.is_testnet)
    db.add(key)
    await db.commit()
    return {"id": key.id, "label": key.label}


@router.delete("/me/api-keys/{key_id}", status_code=204)
async def delete_api_key(key_id: str, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    await db.execute(delete(ExchangeApiKey).where(ExchangeApiKey.id == key_id,
                                                  ExchangeApiKey.user_id == user.id))
    await db.commit()


# -------------------------------------------------------------- notifications

@router.get("/me/notifications")
async def notifications(unread_only: bool = False, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    q = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        q = q.where(Notification.is_read.is_(False))
    rows = (await db.execute(q.order_by(Notification.created_at.desc()).limit(100))).scalars().all()
    return [{"id": n.id, "title": n.title, "body": n.body, "kind": n.kind,
             "is_read": n.is_read, "created_at": n.created_at} for n in rows]


@router.post("/me/notifications/{notif_id}/read", status_code=204)
async def mark_read(notif_id: str, user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    n = await db.get(Notification, notif_id)
    if n is None or n.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    n.is_read = True
    await db.commit()
