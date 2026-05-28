"""
auth.py — Validazione JWT Supabase per Cheruvo.

Come funziona:
  1. Supabase emette un JWT firmato con SUPABASE_JWT_SECRET quando l'utente fa login.
  2. Il frontend lo allega a ogni richiesta come header: Authorization: Bearer <token>
  3. FastAPI chiama get_current_user() come Dependency — se il token manca o è invalido
     risponde 401 prima ancora di entrare nell'endpoint.
  4. require_pro() estende get_current_user() aggiungendo il check sul tier nel DB.
"""

import os
import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_pool

# Il JWT secret si trova in: Supabase Dashboard → Project Settings → API → JWT Secret
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Dependency che valida il Bearer token Supabase.
    Ritorna il payload JWT (contiene 'sub' = user_id UUID, 'email', ecc.)
    Solleva 401 se il token manca, è scaduto o è invalido.
    """
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_JWT_SECRET non configurato nel backend",
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token scaduto — effettua nuovamente il login")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token non valido")


def get_user_tier(user_id: str) -> str:
    """Legge il tier dell'utente dal DB. Ritorna 'pro' o 'free'."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM subscriptions WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        pool.putconn(conn)
    return row[0] if row else "free"


def require_pro(user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency che richiede autenticazione + tier PRO.
    Uso: def endpoint(..., user = Depends(require_pro))
    """
    tier = get_user_tier(user["sub"])
    if tier != "pro":
        raise HTTPException(
            status_code=403,
            detail="Questa funzione richiede un abbonamento PRO",
        )
    return user


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(
        HTTPBearer(auto_error=False)
    ),
) -> dict | None:
    """
    Versione opzionale: non solleva errore se il token manca.
    Utile per endpoint che servono sia utenti anonimi che autenticati
    con comportamenti diversi (es. /api/validate/{ticker}).
    """
    if not credentials or not SUPABASE_JWT_SECRET:
        return None
    try:
        return jwt.decode(
            credentials.credentials,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except Exception:
        return None