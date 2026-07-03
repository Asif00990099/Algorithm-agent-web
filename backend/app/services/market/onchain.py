"""On-chain metrics — keyless free APIs (mempool.space + blockchain.info).

Provides Bitcoin network fundamentals for the dashboard and AI context:
fees, hashrate, difficulty adjustment, mempool depth, tx throughput.
"""
from typing import Optional

from app.services.market.http import cached_get_json

MEMPOOL = "https://mempool.space/api"


async def get_recommended_fees() -> Optional[dict]:
    return await cached_get_json(f"{MEMPOOL}/v1/fees/recommended",
                                 cache_key="onchain:fees", ttl=120)


async def get_difficulty_adjustment() -> Optional[dict]:
    return await cached_get_json(f"{MEMPOOL}/v1/difficulty-adjustment",
                                 cache_key="onchain:difficulty", ttl=600)


async def get_hashrate() -> Optional[dict]:
    return await cached_get_json(f"{MEMPOOL}/v1/mining/hashrate/3d",
                                 cache_key="onchain:hashrate", ttl=1800)


async def get_mempool_stats() -> Optional[dict]:
    return await cached_get_json(f"{MEMPOOL}/mempool",
                                 cache_key="onchain:mempool", ttl=120)


async def get_blockchain_stats() -> Optional[dict]:
    """blockchain.info aggregate stats: tx count, trade volume, miners revenue."""
    return await cached_get_json("https://api.blockchain.info/stats",
                                 cache_key="onchain:stats", ttl=1800)


async def get_onchain_dashboard() -> dict:
    """Everything available in one payload; sources that fail return null."""
    fees = await get_recommended_fees()
    difficulty = await get_difficulty_adjustment()
    hashrate = await get_hashrate()
    mempool = await get_mempool_stats()
    stats = await get_blockchain_stats()

    current_hashrate = None
    if hashrate and hashrate.get("currentHashrate"):
        current_hashrate = round(hashrate["currentHashrate"] / 1e18, 2)  # EH/s

    return {
        "asset": "BTC",
        "fees_sat_vb": fees,                       # fastest/halfHour/hour/economy
        "difficulty_adjustment": difficulty,        # progress %, estimated change
        "hashrate_ehs": current_hashrate,
        "mempool": {
            "tx_count": mempool.get("count") if mempool else None,
            "vsize_mb": round(mempool["vsize"] / 1e6, 2) if mempool and mempool.get("vsize") else None,
        },
        "network": {
            "tx_24h": stats.get("n_tx") if stats else None,
            "btc_sent_24h": round(stats["total_btc_sent"] / 1e8, 2) if stats and stats.get("total_btc_sent") else None,
            "miners_revenue_usd": stats.get("miners_revenue_usd") if stats else None,
            "market_price_usd": stats.get("market_price_usd") if stats else None,
        },
    }
