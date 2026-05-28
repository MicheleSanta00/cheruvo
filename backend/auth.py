"""
auth.py — Validazione JWT Supabase per Cheruvo.
"""

import os
import jwt
import base64
import json
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_pool

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")

security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)


def _decode_payload_no_verify(token: str) -> dict | None:
    """Decodifica il payload JWT senza verificare la firma (solo per diagnostica)."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return None


def _verify_token(token: str) -> dict:
    """
    Verifica il token Supabase e ritorna il payload.
    Distingue tra errori di configurazione (500) e token non validi (401).
    """
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_JWT_SECRET non configurato su Render — vai su Environment Variables e aggiungilo.",
        )

    try:
        return jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token scaduto — effettua nuovamente il login",
        )

    except jwt.InvalidSignatureError:
        # La firma non corrisponde: SUPABASE_JWT_SECRET su Render è sbagliato.
        # Decodifica il payload senza verifica per mostrare info diagnostiche.
        payload = _decode_payload_no_verify(token)
        hint = ""
        if payload:
            hint = f" (token emesso da: {payload.get('iss', 'sconosciuto')}, sub: {str(payload.get('sub',''))[:8]}...)"
        raise HTTPException(
            status_code=500,
            detail=(
                f"SUPABASE_JWT_SECRET su Render non corrisponde alla chiave Supabase.{hint} "
                "Verifica: Supabase Dashboard → Project Settings → API → JWT Secret."
            ),
        )

    except jwt.DecodeError:
        raise HTTPException(status_code=401, detail="Token malformato")

    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Token non valido: {str(e)}")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    return _verify_token(credentials.credentials)


def get_user_tier(user_id: str) -> str:
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT status FROM subscriptions WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
    finally:
        pool.putconn(conn)
    return row[0] if row else "free"


def require_pro(user: dict = Depends(get_current_user)) -> dict:
    tier = get_user_tier(user["sub"])
    if tier != "pro":
        raise HTTPException(
            status_code=403,
            detail="Questa funzione richiede un abbonamento PRO",
        )
    return user


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security_optional),
) -> dict | None:
    if not credentials or not SUPABASE_JWT_SECRET:
        return None
    try:
        return jwt.decode(
            credentials.credentials,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except Exception:
        return None