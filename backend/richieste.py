"""
richieste.py — Chi sta chiedendo, e che cosa.

Tre controlli che valgono per ogni richiesta e che stanno qui, fuori da
main.py, per la stessa ragione di giornaliero.py e payload.py: sono funzioni
pure, e una funzione pura dentro il file che possiede l'applicazione si prova
solo tirandosi dietro FastAPI, il pool di connessioni e l'ordine di import.

    ticker_valido       il simbolo ha una forma possibile?
    PERIODI_AMMESSI     i periodi del grafico che prices.py conosce
    get_user_identifier la chiave del limitatore di richieste
"""
import re

from fastapi import HTTPException, Request
from slowapi.util import get_remote_address

from auth import utente_in_memoria


# ── Il simbolo, controllato una volta sola ────────────────────────────────
#
# Fino al 24 settembre 2026 il simbolo arrivava dall'indirizzo e finiva cosi'
# com'era dentro le URL verso Yahoo, dentro le chiavi di cache e, attraverso
# /api/fetch, dentro l'archivio: una stringa qualunque diventava un "titolo"
# con le sue righe nel database. I simboli veri (NVDA, ENI.MI, BRK.B,
# BTC-USD, ^GSPC, EURUSD=X) stanno tutti dentro questa forma, e il piu' lungo
# dei 302 dell'elenco ne ha undici.
_TICKER_VALIDO = re.compile(r"^[A-Z0-9^][A-Z0-9.=^\-]{0,19}$")


def ticker_valido(ticker: str) -> str:
    """Il simbolo in maiuscolo, oppure un 400 se non puo' essere un simbolo."""
    t = (ticker or "").strip().upper()
    if not _TICKER_VALIDO.match(t):
        raise HTTPException(status_code=400, detail="Simbolo non valido")
    return t


# Solo i periodi che `prices.py` conosce davvero: prima una stringa qualsiasi
# passava, diventava una chiave di cache nuova e ripiegava in silenzio su tre
# mesi.
PERIODI_AMMESSI = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y"}


# ── La chiave del limitatore ──────────────────────────────────────────────
#
# DUE DIFETTI, trovati il 24 settembre 2026.
#
# 1. Il token veniva letto SENZA verificarne la firma. Sugli endpoint
#    pubblici (validate, news, prices, sentiment) un token inventato non
#    viene respinto, perche' `get_current_user_optional` lo tratta come un
#    visitatore anonimo; ma la chiave del limite la sceglieva lui. Bastava
#    mettere un `sub` a caso diverso a ogni richiesta per avere un secchio
#    nuovo ogni volta, cioe' nessun limite. E dietro /validate e /prices c'e'
#    Yahoo: martellato da un indirizzo solo, quello di Render, prima o poi
#    risponde 429 a tutti.
#
# 2. L'indirizzo. Render mette un suo proxy davanti al servizio, e uvicorn,
#    di suo, si fida delle intestazioni inoltrate solo se arrivano da
#    127.0.0.1. Quindi `request.client.host` e' l'indirizzo del proxy, lo
#    stesso per tutti: i visitatori anonimi condividevano UN secchio. Venti
#    persone arrivate insieme da un post si sarebbero divise venti richieste
#    al minuto su /api/news, proprio nel giorno in cui conta.
#
# Adesso l'identita' dell'utente vale solo se Supabase l'ha verificata (vedi
# `auth.utente_in_memoria`; il limitatore gira dopo le dipendenze, quindi il
# token della richiesta corrente e' gia' stato controllato). Altrimenti conta
# il primo indirizzo di X-Forwarded-For, che Render dichiara di impostare al
# client reale ("we set the first IP in the list to the real client IP",
# feedback.render.com, richiesta "Send the correct X_FORWARDED_FOR").
#
# Il rischio che resta va detto: se un giorno Render smettesse di farlo, un
# client potrebbe scriversi un indirizzo finto e tornare al caso 1. Non e'
# peggio di prima, e per controllarlo basta stampare una volta l'intestazione.
def ip_cliente(request: Request) -> str:
    inoltrato = request.headers.get("x-forwarded-for", "") or ""
    primo = inoltrato.split(",")[0].strip()
    return primo or get_remote_address(request)


def get_user_identifier(request: Request) -> str:
    intestazione = request.headers.get("Authorization", "") or ""
    if intestazione.startswith("Bearer "):
        utente = utente_in_memoria(intestazione[7:])
        if utente and utente.get("sub"):
            return f"user:{utente['sub']}"
    return ip_cliente(request)
