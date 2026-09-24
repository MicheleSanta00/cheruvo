"""
auth.py — Validazione JWT via Supabase API (non richiede SUPABASE_JWT_SECRET).

Invece di verificare la firma JWT localmente con PyJWT, delega la verifica
a Supabase chiamando /auth/v1/user. Più robusto, zero config su Render:
bastano SUPABASE_URL e SUPABASE_ANON_KEY (le stesse già usate dal frontend).
"""

import hashlib
import logging
import os
import time
import httpx
import jwt as pyjwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_pool

logger = logging.getLogger(__name__)

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


# ── Token gia' verificati ─────────────────────────────────────────────────
#
# PERCHE', 24 settembre 2026.
#
# Ogni richiesta di un utente con l'account aperto passava da qui, e qui
# faceva una chiamata di rete a Supabase: anche per leggere le notizie, che
# sono pubbliche. Aprire un titolo sono quattro richieste in fila (validate,
# news, prices, sentiment), quindi quattro viaggi andata e ritorno verso
# Supabase prima di mostrare un numero, ognuno con la sua stretta di mano TLS.
#
# Qui si ricorda per un minuto che quel token e' stato verificato davvero.
# Il rischio che si accetta e' preciso: un'uscita dall'account puo' restare
# valida fino a sessanta secondi. Il token non viene mai creduto sulla
# parola: entra in questo elenco SOLO dopo che Supabase ha risposto 200.
#
# Serve anche al limitatore di richieste in main.py, che per la stessa
# ragione non deve fidarsi di un token che nessuno ha controllato.
DURATA_VERIFICA = 60          # secondi
MASSIMO_TOKEN_IN_MEMORIA = 2000
_token_verificati: dict[str, tuple[dict, float]] = {}


def _impronta(token: str) -> str:
    """Il token non si tiene in chiaro nemmeno in memoria: basta l'impronta."""
    return hashlib.sha256((token or "").encode()).hexdigest()


def _scadenza_dichiarata(token: str) -> float | None:
    """
    Il campo `exp` del token, letto SENZA verificare la firma.

    Si usa solo per ACCORCIARE la durata in memoria, mai per allungarla o per
    fidarsi di qualcosa: la verifica vera l'ha gia' fatta Supabase.
    """
    try:
        exp = pyjwt.decode(token, options={"verify_signature": False}).get("exp")
        return float(exp) if exp else None
    except Exception:
        return None


def utente_in_memoria(token: str | None) -> dict | None:
    """L'utente di un token verificato da poco, oppure None."""
    if not token:
        return None
    voce = _token_verificati.get(_impronta(token))
    if not voce:
        return None
    utente, scade = voce
    if time.time() >= scade:
        _token_verificati.pop(_impronta(token), None)
        return None
    return utente


def _ricorda(token: str, utente: dict) -> None:
    if len(_token_verificati) >= MASSIMO_TOKEN_IN_MEMORIA:
        # Svuotare tutto e' grossolano ma sicuro: il costo e' una verifica in
        # piu' per chi torna, mai un token creduto senza controllo.
        _token_verificati.clear()
    scade = time.time() + DURATA_VERIFICA
    exp = _scadenza_dichiarata(token)
    if exp is not None:
        scade = min(scade, exp)
    _token_verificati[_impronta(token)] = (utente, scade)


async def _verify_with_supabase(token: str) -> dict:
    """
    Chiama Supabase /auth/v1/user con il Bearer token.
    Supabase verifica la firma internamente — nessun JWT_SECRET necessario.
    Ritorna il dict utente con 'sub' = user_id UUID.

    SUPABASE CHE NON RISPONDE NON E' UN TOKEN SCADUTO (24 settembre 2026).

    Un timeout o una connessione rifiutata uscivano da qui come eccezione di
    httpx, cioe' come errore 500. Sugli endpoint PUBBLICI era il danno
    peggiore: `get_current_user_optional` intercetta solo HTTPException,
    quindi un utente con l'account aperto riceveva un 500 sulle notizie
    proprio mentre un visitatore anonimo le leggeva senza problemi.

    Adesso diventa un 503. Non un 401, di proposito: `apiFetch.js` a un 401
    risponde disconnettendo l'utente, e un intoppo di rete di Supabase non e'
    un buon motivo per buttare fuori qualcuno.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(
            status_code=500,
            detail=(
                "SUPABASE_URL o SUPABASE_ANON_KEY non configurati su Render. "
                "Aggiungili in Environment Variables."
            ),
        )

    gia_visto = utente_in_memoria(token)
    if gia_visto is not None:
        return gia_visto

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": SUPABASE_ANON_KEY,
                },
            )
    except httpx.HTTPError as e:
        logger.warning("Verifica token non riuscita per un problema di rete: %s", e)
        raise HTTPException(status_code=503,
                            detail="Servizio di accesso momentaneamente non raggiungibile")

    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Token scaduto — effettua nuovamente il login")
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Autenticazione fallita")

    data = r.json()
    if not isinstance(data, dict) or not data.get("id"):
        raise HTTPException(status_code=401, detail="Autenticazione fallita")
    # Normalizza: 'sub' = user_id, compatibile con il resto del codice
    utente = {
        "sub":   data["id"],
        "email": data.get("email", ""),
        **data,
    }
    _ricorda(token, utente)
    return utente


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

    LA REGOLA ERA SCRITTA GIUSTA E APPLICATA A META' (24 settembre 2026).

    Con il paywall spento un iscritto senza abbonamento vale "pro"
    (`get_user_tier` qui sotto), ma chi non aveva un account riceveva "free"
    scritto a mano. Quindi il visitatore NON vedeva quello che vede un
    iscritto: storico delle notizie tagliato a trenta giorni e i periodi 6M e
    1A del grafico respinti con un 403. E il frontend, che parte da
    `isPro = true`, quei bottoni glieli mostrava lo stesso: cliccandoli usciva
    un grafico vuoto, senza una parola. La striscia in cima all'app gli
    diceva intanto "i dati sono gli stessi".

    Adesso la frase del titolo vale in tutti e due gli stati del paywall.
    """
    if not user or not user.get("sub"):
        return _tier_senza_abbonamento()
    return get_user_tier(user["sub"])


def _tier_senza_abbonamento() -> str:
    """
    Cosa vede chi non paga. Letto a ogni chiamata e non fissato all'import,
    cosi' un test (o un domani un interruttore) puo' cambiarlo.
    """
    return "free" if PAYWALL_ATTIVO else "pro"


def get_user_tier(user_id: str) -> str:
    if not PAYWALL_ATTIVO:
        return _tier_senza_abbonamento()

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