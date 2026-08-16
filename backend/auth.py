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


# ── Paywall: spento ───────────────────────────────────────────────────────
#
# Il 6 agosto 2026 il piano a pagamento è stato aperto a tutti. Il motivo non è
# generosità: gli abbonati erano zero, quindi quel muro non stava proteggendo
# nessun ricavo. Stava solo togliendo funzioni alle uniche persone da cui si
# può imparare qualcosa, e in cambio non dava niente.
#
# La domanda a cui serve rispondere adesso non è "quanto pagano" ma "chi lo usa
# e perché", e quella risposta la danno solo gli utenti. Quando ci saranno,
# rimettere il muro è UNA riga: basta togliere questo interruttore.
#
# Tutto il resto (Stripe, la tabella subscriptions, i controlli) è rimasto al
# suo posto e continua a funzionare: chi si abbonasse davvero verrebbe
# registrato come prima. Cambia solo che non serve.
PAYWALL_ATTIVO = os.environ.get("PAYWALL_ATTIVO", "").strip().lower() in ("1", "true", "yes")


def tier_di(user: dict | None) -> str:
    """
    Il tier di chi sta chiedendo, compreso chi non ha un account.

    CHI NON E' REGISTRATO VALE COME UN REGISTRATO SENZA ABBONAMENTO.

    Il 16 agosto 2026, su r/ItaliaStartups: "Rimuovi il Login wall, voglio
    vedere prima di iscrivermi". `App.jsx` rimandava alla schermata di accesso
    CHIUNQUE, quindi del prodotto non si vedeva niente prima di registrarsi, e
    chi non lo prova non si registra.

    La prima versione di questa funzione inventava un tier "visita" con sette
    giorni di storico. Era una decisione di prodotto travestita da correzione
    di un difetto: il compito era togliere il muro, non riscrivere cosa si
    compra registrandosi. Quel ragionamento si fa quando c'e' un motivo per
    farlo, non di straforo mentre se ne sistema un altro.

    Quindi niente livelli nuovi: chi passa vede quello che vede un iscritto
    senza abbonamento. Registrarsi serve gia' per la watchlist, gli alert,
    l'export, la chat e il pulsante di aggiornamento, che restano dove sono.
    """
    if not user or not user.get("sub"):
        return "free"
    return get_user_tier(user["sub"])


def get_user_tier(user_id: str) -> str:
    if not PAYWALL_ATTIVO:
        return "pro"

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