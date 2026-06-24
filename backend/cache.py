"""
cache.py — Cache layer con Redis (Upstash) e fallback in-memory.

Configurazione:
  - Imposta REDIS_URL nelle env vars (es. rediss://user:pass@host:port)
  - Se REDIS_URL non è presente, usa automaticamente la cache in-memory (comportamento precedente)

Upstash free tier: 256MB, zero costi fino a 10k req/giorno — sufficiente per Cheruvo.
Come ottenere l'URL: console.upstash.com → crea database → copia "Redis URL"
"""
import os
import json
import time
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── TTL costanti ───────────────────────────────────────────────────────────────
CACHE_TTL     = 300       # 5 minuti — default per news, prezzi, sentiment
SUMMARY_TTL   = 6 * 3600  # 6 ore — per AI summary (costoso da ricalcolare)
VALIDATE_TTL  = 3600      # 1 ora — info ticker cambiano poco
TICKERS_TTL   = 600       # 10 minuti — lista ticker nel DB

# ── Client Redis (lazy init) ───────────────────────────────────────────────────
_redis_client = None
_redis_available: bool | None = None   # None = non ancora testato


def _get_client():
    """
    Restituisce il client Redis se disponibile, None altrimenti.
    Il test di connessione avviene una sola volta all'avvio.
    """
    global _redis_client, _redis_available

    if _redis_available is not None:
        return _redis_client if _redis_available else None

    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        logger.info("REDIS_URL non impostato — uso cache in-memory")
        _redis_available = False
        return None

    try:
        import redis as redis_lib
        client = redis_lib.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        client.ping()
        _redis_client = client
        _redis_available = True
        logger.info("Redis connesso correttamente (%s)", url.split("@")[-1])
    except Exception as e:
        logger.warning("Redis non disponibile (%s) — fallback in-memory", e)
        _redis_available = False

    return _redis_client if _redis_available else None


# ── Fallback in-memory ─────────────────────────────────────────────────────────
_local: dict[str, dict] = {}


# ── API pubblica ───────────────────────────────────────────────────────────────

def cache_get(key: str, ttl: int = CACHE_TTL) -> Any | None:
    """
    Legge un valore dalla cache.
    Restituisce None se il valore non esiste o è scaduto.
    """
    r = _get_client()

    if r:
        try:
            raw = r.get(key)
            if raw is not None:
                return json.loads(raw)
            return None
        except Exception as e:
            logger.warning("Redis GET error per '%s': %s", key, e)
            # Fallthrough al fallback in-memory

    # In-memory fallback
    entry = _local.get(key)
    if entry and (time.time() - entry["ts"]) < ttl:
        return entry["data"]
    return None


def cache_set(key: str, data: Any, ttl: int = CACHE_TTL) -> None:
    """
    Salva un valore nella cache con il TTL specificato (secondi).
    """
    r = _get_client()

    if r:
        try:
            r.setex(key, ttl, json.dumps(data, default=str))
            return
        except Exception as e:
            logger.warning("Redis SET error per '%s': %s", key, e)
            # Fallthrough al fallback in-memory

    # In-memory fallback
    _local[key] = {"data": data, "ts": time.time(), "ttl": ttl}


def cache_delete_pattern(pattern: str) -> None:
    """
    Invalida tutte le chiavi che contengono il pattern (es. ticker).
    Usato dopo un fetch per forzare il refresh dei dati.
    """
    r = _get_client()

    if r:
        try:
            # SCAN è preferibile a KEYS in produzione (non blocca Redis)
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = r.scan(cursor, match=f"*{pattern}*", count=100)
                if keys:
                    r.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            if deleted:
                logger.info("Cache Redis: %d chiavi eliminate per pattern '%s'", deleted, pattern)
            return
        except Exception as e:
            logger.warning("Redis SCAN/DEL error: %s", e)

    # In-memory fallback
    to_del = [k for k in _local if pattern in k]
    for k in to_del:
        _local.pop(k, None)
    if to_del:
        logger.info("Cache in-memory: %d chiavi eliminate per pattern '%s'", len(to_del), pattern)


def cache_stats() -> dict:
    """Restituisce statistiche sulla cache (usato nell'endpoint /health)."""
    r = _get_client()
    if r:
        try:
            info = r.info("memory")
            return {
                "backend": "redis",
                "used_memory_human": info.get("used_memory_human", "N/A"),
                "connected_clients": r.info("clients").get("connected_clients", "N/A"),
            }
        except Exception:
            pass
    return {
        "backend": "in-memory",
        "entries": len(_local),
    }
