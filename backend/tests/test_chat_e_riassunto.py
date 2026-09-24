"""
La chat e il riassunto: le due cose che passano da Groq a richiesta di un
utente, e quindi le due che possono consumare la quota o bloccare il server.

Difetti chiusi il 24 settembre 2026:
  - la chat accettava messaggi di qualunque lunghezza;
  - la chat era `async` con una chiamata bloccante dentro, quindi fermava il
    server per tutti mentre il modello scriveva;
  - con i GPT-OSS (dal 16 agosto) il tetto di token era troppo basso e la
    risposta poteva arrivare vuota, o il JSON del riassunto tagliato;
  - il riassunto di ripiego dava consigli ("si consiglia cautela").
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")
os.environ.setdefault("GROQ_API_KEY", "gsk_fake_key_for_tests")

import inspect
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def app():
    pool = MagicMock()
    with patch("database.get_pool", return_value=pool), \
         patch("database._get_connection"):
        from main import app as _app
        yield _app
        _app.dependency_overrides.clear()


@pytest.fixture
def con_utente(app):
    from auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {"sub": "u1", "email": "a@b.c"}
    yield
    app.dependency_overrides.clear()


def _groq_che_risponde(testo):
    finto = MagicMock()
    risposta = MagicMock()
    risposta.choices = [MagicMock(message=MagicMock(content=testo))]
    finto.chat.completions.create.return_value = risposta
    return finto


def test_la_chat_non_e_piu_una_funzione_async(app):
    """
    Una chiamata bloccante dentro `async def` ferma il ciclo di eventi.

    Chiede `app` anche se non lo usa: importare `main` fuori dal patch del
    pool lo metterebbe in cache con il pool vero, e il test dopo proverebbe a
    connettersi a un database (la trappola scritta in cima a giornaliero.py).
    """
    import main
    assert not inspect.iscoroutinefunction(main.chat.__wrapped__
                                           if hasattr(main.chat, "__wrapped__")
                                           else main.chat)
    assert not inspect.iscoroutinefunction(
        main.onboarding_welcome.__wrapped__
        if hasattr(main.onboarding_welcome, "__wrapped__")
        else main.onboarding_welcome)


def test_un_messaggio_enorme_non_arriva_a_groq(app, con_utente):
    finto = _groq_che_risponde("ciao")
    with patch("sentiment_groq._get_groq", return_value=finto):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post("/api/chat", json={"message": "x" * 5000})
    assert resp.status_code == 422
    assert not finto.chat.completions.create.called


def test_una_risposta_vuota_e_un_errore_non_un_fumetto_vuoto(app, con_utente):
    finto = _groq_che_risponde("")
    with patch("sentiment_groq._get_groq", return_value=finto):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post("/api/chat", json={"message": "cos'e' il sentiment?"})
    assert resp.status_code == 503


def test_la_chat_lascia_spazio_al_ragionamento(app, con_utente):
    finto = _groq_che_risponde("Il sentiment e' il tono delle notizie.")
    with patch("sentiment_groq._get_groq", return_value=finto):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post("/api/chat", json={"message": "spiegami",
                                             "ticker": "NVDA",
                                             "top_news": ["a" * 1000, "b", "c", "d"]})
    assert resp.status_code == 200
    assert resp.json()["reply"].startswith("Il sentiment")
    argomenti = finto.chat.completions.create.call_args.kwargs
    assert argomenti["max_tokens"] >= 1500
    # I titoli passati come contesto vengono accorciati, e ne entrano tre.
    sistema = argomenti["messages"][0]["content"]
    assert "a" * 301 not in sistema
    assert "; d" not in sistema


# ── Il riassunto ──────────────────────────────────────────────────────────

def test_il_ripiego_descrive_e_non_consiglia():
    from summary import _fallback
    for media in (0.4, -0.4, 0.0):
        testo = _fallback(media)["riassunto"].lower()
        for vietata in ("consiglia", "cautela", "supporto", "attendere",
                        "compra", "vendi", "ribassist", "favorevole"):
            assert vietata not in testo, (media, vietata)
        assert "non una previsione" in testo


def test_il_json_fra_backtick_si_legge_lo_stesso():
    import summary
    corpo = ('```json\n{"giudizio": "neutro", "riassunto": "Le notizie parlano '
             'di un accordo commerciale e dei conti.", "temi": ["a", "b", "c"]}\n```')
    with patch.object(summary, "client", _groq_che_risponde(corpo)):
        r = summary.genera_summary("NVDA", "NVIDIA", ["titolo"], 0.0)
    assert r["fonte"].startswith("groq/")
    assert r["temi"] == ["a", "b", "c"]


def test_una_risposta_vuota_ripiega_senza_esplodere():
    import summary
    with patch.object(summary, "client", _groq_che_risponde(None)):
        r = summary.genera_summary("NVDA", "NVIDIA", ["titolo"], 0.3)
    assert r["fonte"] == "fallback"


def test_il_riassunto_non_chiede_previsioni_sul_prezzo():
    from summary import PROMPT_TEMPLATE
    assert "prospettiva di breve periodo" not in PROMPT_TEMPLATE
    assert "niente previsioni sul prezzo" in PROMPT_TEMPLATE


def test_senza_chiave_groq_il_modulo_si_importa_lo_stesso():
    """
    Prima il client nasceva all'import: senza GROQ_API_KEY il costruttore di
    Groq sollevava, e con lui cadeva l'intero backend.
    """
    import importlib
    import summary
    with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
        importlib.reload(summary)
    importlib.reload(summary)
