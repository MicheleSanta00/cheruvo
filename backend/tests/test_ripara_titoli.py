"""
Test della riparazione dei titoli con entità HTML.

Questo script riscrive dati di produzione, quindi il rischio non è che si
rompa: è che rovini titoli che stavano bene. Due modi di rovinarli, tutti e
due silenziosi.

Il primo è riconoscere come entità qualcosa che non lo è: "AT&T Q2 earnings"
contiene una "&" e non va toccato. Il secondo è decodificare due volte, che
trasforma "&amp;lt;" prima in "&lt;" e poi in "<".
"""
import ripara_titoli as rt


# ── Cosa viene riconosciuto come entità ───────────────────────────────────
def test_riconosce_le_entita_vere():
    assert rt.ENTITA.search("H&#xFC;fte verschlissen")
    assert rt.ENTITA.search("&#128512; buone notizie")
    assert rt.ENTITA.search("Fiat &amp; Chrysler")


def test_non_scambia_una_e_commerciale_per_un_entita():
    """
    Il falso positivo che rovinerebbe titoli sani. Sono nomi di aziende
    ricorrenti in un archivio finanziario, non casi di scuola.
    """
    for t in ("AT&T reports Q2 earnings",
              "Johnson & Johnson shares rise",
              "Standard & Poor's cuts the outlook",
              "R&D spending up 12%"):
        assert not rt.ENTITA.search(t), t


# ── La decodifica ─────────────────────────────────────────────────────────
def test_decodifica_i_caratteri_non_inglesi():
    assert rt._decodifica("H&#xFC;fte verschlissen") == "Hüfte verschlissen"
    assert rt._decodifica("PRETU&#x10C;ENOG") == "PRETUČENOG"


def test_una_passata_sola_e_non_due():
    """
    "&amp;lt;" decodificato una volta dà "&lt;", che è il testo giusto.
    Decodificato due volte dà "<", cioè marcatura dentro un campo di testo.
    """
    assert rt._decodifica("&amp;lt;b&amp;gt;") == "&lt;b&gt;"


def test_un_titolo_gia_pulito_resta_identico():
    """
    Serve a poter rilanciare lo script senza paura: se non cambia niente, la
    riga non viene nemmeno scritta.
    """
    t = "Bitcoin hits new record high"
    assert rt._decodifica(t) == t
