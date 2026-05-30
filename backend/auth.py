"""
auth.py — Validazione JWT via Supabase API (non richiede SUPABASE_JWT_SECRET).

Invece di verificare la firma JWT localmente con PyJWT, delega la verifica
a Supabase chiamando /auth/v1/user. Più robusto, zero config su Render:
bastano SUPABASE_URL e SUPABASE_ANON_KEY (le stesse già usate dal frontend).
"""

import os
import time
import httpx
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_pool

# ── Cache tier utente ──────────────────────────────────────────────────────
# Evita una query DB a ogni richiesta autenticata.
# TTL di 5 minuti: il tier viene aggiornato immediatamente dallo Stripe webhook,
# quindi al massimo 5 minuti di lag dopo un upgrade/downgrade manuale.
_tier_cache: dict[str, tuple[str, float]] = {}  # {user_id: (tier, timestamp)}
TIER_CACHE_TTL = 300  # 5 minuti


def _get_cached_tier(user_id: str) -> str | None:
    entry = _tier_cache.get(user_id)
    if entry and time.time() - entry[1] < TIER_CACHE_TTL:
        return entry[0]
    return None


def _set_cached_tier(user_id: str, tier: str) -> None:
    _tier_cache[user_id] = (tier, time.time())


def invalidate_tier_cache(user_id: str) -> None:
    """Chiamare dopo un upgrade/downgrade Stripe per invalidare subito la cache."""
    _tier_cache.pop(user_id, None)

SUPABASE_URL     = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

security          = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)


async def _verify_with_supabase(token: str) -> dict:
    """
    Chiama Supabase /auth/v1/user con il Bearer token.
    Supabase verifica la firma internamente — nessun JWT_SECRET necessario.
    Ritorna il dict utente con 'sub' = user_id UUID.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(
            status_code=500,
            detail=(
                "SUPABASE_URL o SUPABASE_ANON_KEY non configurati su Render. "
                "Aggiungili in Environment Variables."
            ),
        )

    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": SUPABASE_ANON_KEY,
            },
        )

    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Token scaduto — effettua nuovamente il login")
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Autenticazione fallita")

    data = r.json()
    # Normalizza: 'sub' = user_id, compatibile con il resto del codice
    return {
        "sub":   data["id"],
        "email": data.get("email", ""),
        **data,
    }


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    return await _verify_with_supabase(credentials.credentials)


def get_user_tier(user_id: str) -> str:
    cached = _get_cached_tier(user_id)
    if cached is not None:
        return cached

    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT status FROM subscriptions WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
    finally:
        pool.putconn(conn)

    tier = row[0] if row else "free"
    _set_cached_tier(user_id, tier)
    return tier


async def require_pro(user: dict = Depends(get_current_user)) -> dict:
    tier = get_user_tier(user["sub"])
    if tier != "pro":
        raise HTTPException(
            status_code=403,
            detail="Questa funzione richiede un abbonamento PRO",
        )
    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security_optional),
) -> dict | None:
    if not credentials:
        return None
    try:
        return await _verify_with_supabase(credentials.credentials)
    except HTTPException:
        return None