"""
I modelli Groq: che non ne resti in giro uno spento.

Il 16 agosto 2026 Groq ha dismesso lo stesso giorno `llama-3.3-70b-versatile`
(i punteggi) e `llama-3.1-8b-instant` (riassunti e backfill). Il nome del
modello era scritto a mano in quattro file piu' un workflow, quindi accorgersi
di averne dimenticato uno sarebbe successo solo vedendo i punteggi sparire
dall'app.

Questi test non provano che il modello nuovo funzioni: quello lo dice solo una
chiamata vera. Provano che non ne sia rimasto indietro uno morto, che e' il
modo in cui questa migrazione poteva fallire in silenzio.
"""
import pathlib
import re

import sentiment_groq as sg

RADICE = pathlib.Path(__file__).resolve().parents[2]

# Dismessi da Groq il 16 agosto 2026.
SPENTI = ("llama-3.3-70b-versatile", "llama-3.1-8b-instant")


def _file_di_codice():
    for pattern in ("backend/*.py", "*.py", ".github/workflows/*.yml"):
        for f in RADICE.glob(pattern):
            if "test" not in f.name:
                yield f


def test_nessun_modello_spento_e_rimasto_nel_codice():
    colpevoli = []
    for f in _file_di_codice():
        testo = f.read_text(encoding="utf-8", errors="replace")
        for riga in testo.splitlines():
            spogliata = riga.strip()
            # I commenti possono nominarli: e' la storia di come ci siamo
            # arrivati, e cancellarla per far passare un test sarebbe il modo
            # sbagliato di tenere pulito il codice.
            if spogliata.startswith("#"):
                continue
            if any(m in riga for m in SPENTI):
                colpevoli.append(f"{f.name}: {spogliata[:70]}")
    assert not colpevoli, "modelli dismessi ancora in uso:\n  " + "\n  ".join(colpevoli)


def test_i_modelli_scelti_sono_di_produzione():
    """
    Groq suggeriva anche qwen3.6-27b, che pero' e' fra i PREVIEW e la loro
    stessa pagina dice di non usarli in produzione perche' possono sparire con
    poco preavviso. Cioe' come ci siamo trovati oggi.
    """
    assert sg.MODELLO_PUNTEGGIO.startswith("openai/gpt-oss")
    assert sg.MODELLO_VELOCE.startswith("openai/gpt-oss")
    assert "qwen" not in (sg.MODELLO_PUNTEGGIO + sg.MODELLO_VELOCE).lower()


def test_il_modello_si_puo_cambiare_da_variabile_d_ambiente(monkeypatch):
    """
    Se Groq ne spegne un altro, deve bastare una variabile su Render senza
    aspettare un deploy.
    """
    import importlib
    monkeypatch.setenv("GROQ_SCORE_MODEL", "un/modello-qualsiasi")
    ricaricato = importlib.reload(sg)
    assert ricaricato.MODELLO_PUNTEGGIO == "un/modello-qualsiasi"
    monkeypatch.delenv("GROQ_SCORE_MODEL")
    importlib.reload(sg)


def test_il_budget_di_token_tiene_conto_del_ragionamento():
    """
    I GPT-OSS ragionano prima di rispondere e quei token consumano lo stesso
    budget. Col tetto vecchio (120 + 20 per articolo) un lotto da venti aveva
    520 token: il ragionamento se li poteva mangiare tutti e lasciare un JSON
    tagliato, cioe' meta' lotto senza punteggio e senza un errore.
    """
    sorgente = pathlib.Path(sg.__file__).read_text(encoding="utf-8")
    m = re.search(r"max_tokens=(\d+) \+ (\d+) \* len\(articles\)", sorgente)
    assert m, "il calcolo di max_tokens e' cambiato: ricontrolla il margine"
    base, per_articolo = int(m.group(1)), int(m.group(2))
    assert base + per_articolo * 20 >= 1200, "budget troppo stretto per un lotto da venti"


def test_i_modelli_scelti_sono_sul_piano_gratuito():
    """
    Cheruvo sta sul piano gratuito di Groq e ci deve restare. La scelta del
    modello non si fa sul prezzo per milione di token, che qui non si paga, ma
    sui limiti del piano gratuito. Entrambi i GPT-OSS ci sono; Qwen3.6 pure, ma
    e' preview.

    Il test guarda che la nota lo dica, perche' il prossimo che cambia modello
    deve trovare scritto il metro giusto e non i prezzi.
    """
    import pathlib
    nota = pathlib.Path(sg.__file__).read_text(encoding="utf-8")
    assert "piano GRATUITO" in nota or "piano gratuito" in nota
    assert "TPD" in nota, "mancano i limiti del piano gratuito nella nota"
