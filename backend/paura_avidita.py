"""
paura_avidita.py — Fear & Greed Index delle criptovalute.

Perché sta dentro Cheruvo e non è un'aggiunta qualsiasi. È l'indicatore di
umore più conosciuto nel mondo crypto, e soprattutto è una misura del
sentiment INDIPENDENTE dalla nostra: la loro nasce da volatilità, volumi,
dominanza e sondaggi, la nostra dalle notizie. Due misure diverse della stessa
cosa. Quando concordano, la lettura è solida. Quando divergono, quello è il
dato interessante: "i giornali scrivono male ma il mercato è avido" è una
forma che nessuno dei due indicatori, da solo, riesce a mostrare.

Licenza: alternative.me dichiara l'uso libero anche commerciale, con
attribuzione gradita ma non obbligatoria. Gliela mettiamo lo stesso, accanto
al dato: costa una riga ed è corretto verso chi regala un servizio.
Verificato il 4 agosto 2026.
"""
import logging

import requests
from fastapi import APIRouter

from cache import cache_get, cache_set

logger = logging.getLogger(__name__)
router = APIRouter()

URL = "https://api.alternative.me/fng/"
# L'indice si aggiorna una volta al giorno: tenerlo in cache sei ore significa
# quattro chiamate al giorno invece di una per ogni visita.
TTL = 6 * 3600

# Le etichette arrivano in inglese: le traduciamo qui, una volta sola.
TRADUZIONI = {
    "Extreme Fear": ("Paura estrema", "#dc2626"),
    "Fear":         ("Paura", "#f97316"),
    "Neutral":      ("Neutro", "#eab308"),
    "Greed":        ("Avidità", "#84cc16"),
    "Extreme Greed": ("Avidità estrema", "#16a34a"),
}


def _leggi(limite: int = 30) -> dict | None:
    try:
        r = requests.get(URL, params={"limit": limite}, timeout=12)
        r.raise_for_status()
        dati = (r.json() or {}).get("data") or []
        if not dati:
            return None

        def voce(d):
            grezza = d.get("value_classification", "")
            etichetta, colore = TRADUZIONI.get(grezza, (grezza, "#8a94a6"))
            return {
                "valore": int(d.get("value", 0)),
                "etichetta": etichetta,
                "etichetta_en": grezza,
                "colore": colore,
                "quando": int(d.get("timestamp", 0)),
            }

        storico = [voce(d) for d in dati]
        oggi = storico[0]
        # La variazione rispetto a ieri e a una settimana fa: il numero da solo
        # dice poco, "35 e in salita" e "35 in caduta da 70" sono due mondi.
        ieri = storico[1]["valore"] if len(storico) > 1 else None
        settimana = storico[7]["valore"] if len(storico) > 7 else None

        return {
            **oggi,
            "vs_ieri": (oggi["valore"] - ieri) if ieri is not None else None,
            "vs_settimana": (oggi["valore"] - settimana) if settimana is not None else None,
            "storico": list(reversed(storico)),   # dal più vecchio al più recente, per il grafico
            "fonte": "alternative.me",
        }
    except Exception as e:
        logger.warning("Fear & Greed non disponibile: %s", e)
        return None


@router.get("/fear-greed")
def fear_greed():
    """
    Indice paura/avidità del mercato crypto. Nessuna autenticazione: è un dato
    pubblico e serve anche alla pagina iniziale.
    Se la fonte non risponde ritorna disponibile=False invece di un errore:
    è un contorno, non deve far fallire la schermata.
    """
    chiave = "fear_greed"
    salvato = cache_get(chiave, ttl=TTL)
    if salvato:
        return salvato

    dati = _leggi()
    if not dati:
        return {"disponibile": False}

    risultato = {"disponibile": True, **dati}
    cache_set(chiave, risultato, ttl=TTL)
    return risultato
