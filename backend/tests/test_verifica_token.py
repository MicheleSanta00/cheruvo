"""
La verifica del token e la chiave del limitatore.

Due difetti trovati il 24 settembre 2026, che si toccano: il limitatore si
fidava di un token che nessuno aveva controllato, e un intoppo di rete verso
Supabase diventava un 500 anche sulle pagine pubbliche.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import jwt as pyjwt
import pytest
from fastapi import HTTPException

import auth


@pytest.fixture(autouse=True)
def memoria_pulita():
    auth._token_verificati.clear()
    with patch("auth.SUPABASE_URL", "https://fake.supabase.co"), \
         patch("auth.SUPABASE_ANON_KEY", "anon"):
        yield
    auth._token_verificati.clear()


def _risposta(stato, corpo=None):
    r = MagicMock()
    r.status_code = stato
    r.json.return_value = corpo or {}
    return r


class _ClientFinto:
    """Un httpx.AsyncClient finto: risponde quello che gli si dice, e conta."""
    chiamate = 0

    def __init__(self, risposta=None, errore=None):
        self._risposta, self._errore = risposta, errore

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        _ClientFinto.chiamate += 1
        if self._errore:
            raise self._errore
        return self._risposta


def _verifica(token):
    return asyncio.run(auth._verify_with_supabase(token))


def test_un_token_verificato_non_torna_da_supabase_per_un_minuto():
    """Quattro richieste per aprire un titolo erano quattro viaggi a Supabase."""
    _ClientFinto.chiamate = 0
    finto = _ClientFinto(_risposta(200, {"id": "u1", "email": "a@b.c"}))
    with patch("auth.httpx.AsyncClient", finto):
        assert _verifica("tok")["sub"] == "u1"
        assert _verifica("tok")["sub"] == "u1"
    assert _ClientFinto.chiamate == 1


def test_un_token_respinto_non_finisce_in_memoria():
    finto = _ClientFinto(_risposta(401))
    with patch("auth.httpx.AsyncClient", finto):
        with pytest.raises(HTTPException) as e:
            _verifica("falso")
    assert e.value.status_code == 401
    assert auth.utente_in_memoria("falso") is None


def test_supabase_irraggiungibile_e_un_503_non_un_500():
    """
    Un 401 farebbe disconnettere l'utente da apiFetch.js: un intoppo di rete
    di Supabase non e' un motivo per buttare fuori qualcuno.
    """
    finto = _ClientFinto(errore=httpx.ConnectTimeout("lento"))
    with patch("auth.httpx.AsyncClient", finto):
        with pytest.raises(HTTPException) as e:
            _verifica("tok")
    assert e.value.status_code == 503


def test_sulle_pagine_pubbliche_supabase_giu_vuol_dire_visitatore():
    """Prima: 500 sulle notizie per chi aveva l'account aperto, 200 per gli altri."""
    finto = _ClientFinto(errore=httpx.ConnectError("giu"))
    credenziali = MagicMock(credentials="tok")
    with patch("auth.httpx.AsyncClient", finto):
        assert asyncio.run(auth.get_current_user_optional(credenziali)) is None


def test_la_memoria_non_supera_la_scadenza_del_token():
    import time
    scade = int(time.time()) + 5
    token = pyjwt.encode({"sub": "u1", "exp": scade}, "segreto", algorithm="HS256")
    auth._ricorda(token, {"sub": "u1"})
    _, fine = auth._token_verificati[auth._impronta(token)]
    assert fine <= scade


def test_il_token_non_si_tiene_in_chiaro():
    auth._ricorda("token-in-chiaro", {"sub": "u1"})
    assert "token-in-chiaro" not in auth._token_verificati


# ── La chiave del limitatore ──────────────────────────────────────────────

def _richiesta(intestazioni=None, host="10.0.0.1"):
    r = MagicMock()
    r.headers = {k.lower(): v for k, v in (intestazioni or {}).items()}
    r.headers = _Intestazioni(r.headers)
    r.client.host = host
    return r


class _Intestazioni(dict):
    """Come quelle di Starlette: si leggono senza badare alle maiuscole."""
    def get(self, k, d=None):
        return super().get(k.lower(), d)


def _chiave(req):
    import richieste
    return richieste.get_user_identifier(req)


def test_un_token_inventato_non_sceglie_la_chiave():
    """
    Il difetto: il `sub` letto senza verificare la firma. Un `sub` a caso a
    ogni richiesta dava un secchio nuovo ogni volta, cioe' nessun limite.
    """
    falso = pyjwt.encode({"sub": "chiunque-io-voglia"}, "x", algorithm="HS256")
    chiave = _chiave(_richiesta({"Authorization": f"Bearer {falso}",
                                 "X-Forwarded-For": "203.0.113.9"}))
    assert "chiunque" not in chiave
    assert chiave == "203.0.113.9"


def test_un_token_verificato_da_supabase_vale_l_utente():
    auth._ricorda("vero", {"sub": "u-verificato"})
    chiave = _chiave(_richiesta({"Authorization": "Bearer vero"}))
    assert chiave == "user:u-verificato"


def test_dietro_il_proxy_di_render_conta_il_client_non_il_proxy():
    """
    Senza questo tutti i visitatori anonimi avevano l'indirizzo del proxy, e
    quindi un secchio solo in comune.
    """
    a = _chiave(_richiesta({"X-Forwarded-For": "198.51.100.1, 10.0.0.1"}))
    b = _chiave(_richiesta({"X-Forwarded-For": "198.51.100.2, 10.0.0.1"}))
    assert a == "198.51.100.1" and b == "198.51.100.2"


def test_senza_intestazioni_si_usa_l_indirizzo_della_connessione():
    assert _chiave(_richiesta(host="127.0.0.1")) == "127.0.0.1"


# ── Il simbolo ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("buono", ["NVDA", "eni.mi", "BRK.B", "BTC-USD",
                                   "^GSPC", "EURUSD=X", "STMMI.MI"])
def test_i_simboli_veri_passano(buono):
    import richieste
    assert richieste.ticker_valido(buono) == buono.upper()


@pytest.mark.parametrize("cattivo", ["", " ", "A" * 21, "AAPL;DROP", "../x",
                                     "<script>", "AAPL?x=1", "-USD"])
def test_i_simboli_impossibili_no(cattivo):
    import richieste
    with pytest.raises(HTTPException) as e:
        richieste.ticker_valido(cattivo)
    assert e.value.status_code == 400
