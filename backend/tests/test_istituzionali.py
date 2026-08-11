"""
Test delle fonti regolatorie.

Il rischio qui non è tecnico, è di licenza e di rumore.

Di licenza, perché BCE ed ESMA permettono il riuso a condizioni precise e una
di quelle condizioni è dichiarare che il materiale è stato modificato.
Calcolare un sentiment È una modifica. Se la provenienza si perde per strada,
si perde anche la possibilità di mostrare la nota dovuta.

Di rumore, perché queste fonti pubblicano soprattutto nomine, concorsi e
calendari. Farli entrare significherebbe riempire l'archivio di righe che non
riguardano nessun mercato, cioè rifare il difetto che il filtro di contesto ha
appena finito di togliere.
"""
import istituzionali as ist
from gdelt_source import TERMINE_QUERY


# ── Cosa entra ────────────────────────────────────────────────────────────
def test_un_comunicato_su_una_moneta_precisa_va_a_quella_moneta():
    r = ist._pertinente("Fed announces approval of Bitcoin spot ETF custody rules",
                        TERMINE_QUERY)
    assert r == ["BTC-USD"]


def test_le_regole_sulle_cripto_in_generale_vanno_alle_due_grandi():
    """
    Un intervento su MiCA riguarda tutto il settore, ma metterlo su venti
    monete gonfierebbe i conteggi e falserebbe le medie: su una alt-coin
    sottile un solo comunicato sposterebbe l'intero punteggio.
    """
    for t in ("ESMA publishes final report on MiCA technical standards",
              "ECB launches digital euro preparation phase",
              "ESMA warns investors about crypto-asset risks"):
        assert ist._pertinente(t, TERMINE_QUERY) == ["BTC-USD", "ETH-USD"], t


# ── Cosa NON entra ────────────────────────────────────────────────────────
def test_il_macro_puro_resta_fuori():
    """
    Una decisione sui tassi riguarda tutto e niente. Attaccarla a ogni moneta
    sarebbe il difetto di GOOGL e MSFT rifatto da capo, con l'aggravante che
    stavolta sarebbe la stessa identica riga ripetuta venti volte.
    """
    assert ist._pertinente("Federal Reserve issues FOMC statement",
                           TERMINE_QUERY) == []


def test_nomine_concorsi_e_calendari_restano_fuori():
    for t in ("Vacancy notice: Senior Legal Officer",
              "Federal Reserve Board announces personnel changes",
              "Speech by Christine Lagarde at the annual conference"):
        assert ist._pertinente(t, TERMINE_QUERY) == [], t


def test_i_working_paper_della_bce_restano_fuori():
    """
    Sono l'eccezione dichiarata nella licenza BCE: i documenti firmati da
    autori richiedono autorizzazione scritta. Vanno tenuti fuori per motivi
    legali, non di rumore.
    """
    assert ist._pertinente("ECB publishes Working Paper on inflation dynamics",
                           TERMINE_QUERY) == []


# ── La provenienza, che è quella che rende la licenza rispettabile ────────
def test_ogni_fonte_dichiara_la_sua_licenza_e_chi_va_citato():
    for nome, f in ist.FONTI.items():
        assert f["licenza"], nome
        assert f["attribuzione"], nome
        assert isinstance(f["serve_disclaimer"], bool), nome


def test_bce_ed_esma_pretendono_il_disclaimer_la_fed_no():
    """
    Non è un dettaglio di stile: BCE ed ESMA chiedono che una modifica venga
    dichiarata, e il sentiment è una modifica. La Fed è pubblico dominio e
    chiede solo di essere citata.
    """
    assert ist.FONTI["BCE"]["serve_disclaimer"] is True
    assert ist.FONTI["ESMA"]["serve_disclaimer"] is True
    assert ist.FONTI["Federal Reserve"]["serve_disclaimer"] is False


def test_il_disclaimer_dice_le_due_cose_che_esma_impone():
    testo = ist.DISCLAIMER.lower()
    assert "elaborazione" in testo, "manca la dichiarazione di modifica"
    assert "non avalla" in testo, "manca il mancato avallo dell'autorità"


# ── Uno zero deve dire quale zero è ───────────────────────────────────────
#
# I primi tre giri del workflow hanno stampato "0 comunicati pertinenti" per
# tutte e tre le fonti, e quella riga non distingueva fra "il feed aveva
# cinquanta comunicati e nessuno parlava di cripto" e "il feed non ha
# risposto". Sono due situazioni opposte: la prima si aspetta, la seconda si
# aggiusta.
class _Feed:
    def __init__(self, entries, bozo=False, eccezione=""):
        self.entries = entries
        self.bozo = bozo
        self.bozo_exception = eccezione


def _voce(titolo, quando):
    import time as _t
    return type("V", (), {"title": titolo, "link": "https://esempio/x",
                          "published_parsed": _t.gmtime(quando)})()


def test_un_feed_vuoto_grida_invece_di_tacere(monkeypatch, caplog):
    import feedparser
    monkeypatch.setattr(feedparser, "parse", lambda *_a, **_k: _Feed([]))
    with caplog.at_level("WARNING"):
        assert ist.leggi("BCE", 3) == []
    # getMessage() applica gli argomenti al template: `record.msg` da solo
    # sarebbe ancora "%-18s NESSUNA VOCE...".
    assert any("NESSUNA VOCE" in r.getMessage() for r in caplog.records), \
        "un feed muto deve lasciare un avviso"


def test_un_feed_pieno_ma_senza_cripto_non_e_un_guasto(monkeypatch, caplog):
    import time
    import feedparser
    adesso = time.time()
    voci = [_voce("ECB appoints new Director General", adesso),
            _voce("Vacancy notice: Senior Legal Officer", adesso),
            _voce("Banking supervision: 2026 stress test calendar", adesso)]
    monkeypatch.setattr(feedparser, "parse", lambda *_a, **_k: _Feed(voci))
    with caplog.at_level("WARNING"):
        assert ist.leggi("BCE", 3) == []
    assert not [r for r in caplog.records if r.levelname == "WARNING"], \
        "un feed che risponde non deve produrre avvisi solo perche' non c'e' cripto"
