"""
Test del confronto fra i due valutatori.

Il rischio qui e' di scrivere nella colonna sbagliata.

`sentiment` e' quello che l'app mostra e che sta in archivio da mesi. Questo
script serve a MISURARE quanto Llama e il tono GDELT sono d'accordo, non a
correggere niente: se per un errore il secondo parere finisse in `sentiment`,
si perderebbe il primo e con lui la possibilita' stessa del confronto.

L'altro rischio e' scrivere numeri finti quando Groq non risponde, che e' lo
stesso difetto per cui a luglio gli score VADER erano stati sovrascritti da
zeri.
"""
from unittest.mock import MagicMock, patch

import calibra


def _pool():
    pool, conn, cur = MagicMock(), MagicMock(), MagicMock()
    conn.cursor.return_value = cur
    pool.getconn.return_value = conn
    return pool, conn, cur


RIGHE = [(1, "NVDA", "Titolo uno", 0.10),
         (2, "NVDA", "Titolo due", -0.20),
         (3, "BTC-USD", "Titolo tre", 0.05)]


# ── Dove finisce il secondo parere ────────────────────────────────────────
def test_il_secondo_parere_non_tocca_la_colonna_originale():
    pool, conn, cur = _pool()
    with patch("database.get_pool", return_value=pool), \
         patch("sentiment_groq.score_batch", return_value=[0.4, -0.6, 0.1]):
        assert calibra.valuta(RIGHE, scrivi=True) == 3

    scritture = " ".join(str(c) for c in cur.executemany.call_args_list)
    assert "sentiment_2" in scritture
    assert "SET sentiment =" not in scritture, \
        "ha scritto nella colonna che l'app mostra"


def test_senza_scrivi_conta_ma_non_tocca_il_database():
    pool, conn, cur = _pool()
    with patch("database.get_pool", return_value=pool), \
         patch("sentiment_groq.score_batch", return_value=[0.4, -0.6, 0.1]):
        assert calibra.valuta(RIGHE, scrivi=False) == 3
    cur.executemany.assert_not_called()
    conn.commit.assert_not_called()


# ── Quando il modello non risponde ────────────────────────────────────────
def test_groq_giu_non_scrive_niente():
    """
    None da score_batch vuol dire "non lo so". Scrivere uno zero al suo posto
    e' il difetto di luglio: uno zero e' un giudizio, l'assenza di risposta no.
    """
    pool, conn, cur = _pool()
    with patch("database.get_pool", return_value=pool), \
         patch("sentiment_groq.score_batch", return_value=None):
        assert calibra.valuta(RIGHE, scrivi=True) == 0
    cur.executemany.assert_not_called()


def test_un_punteggio_mancante_non_sposta_gli_altri():
    """Se il modello salta un articolo, gli altri due vanno comunque scritti."""
    pool, conn, cur = _pool()
    with patch("database.get_pool", return_value=pool), \
         patch("sentiment_groq.score_batch", return_value=[0.4, None, 0.1]):
        assert calibra.valuta(RIGHE, scrivi=True) == 2
    coppie = cur.executemany.call_args[0][1]
    assert [id_ for _, id_ in coppie] == [1, 3], "ha associato i punteggi all'articolo sbagliato"


# ── Il rapporto ───────────────────────────────────────────────────────────
def test_con_pochi_articoli_si_rifiuta_di_dare_un_numero():
    with patch.object(calibra, "coppie_complete",
                      return_value=[("NVDA", "x", 0.1, 0.2, None)] * 10):
        assert calibra.rapporto() == 1


def test_con_abbastanza_articoli_il_numero_esce(capsys):
    coppie = [("NVDA", f"titolo {i}", (i % 7) / 10 - 0.3, (i % 5) / 10 - 0.2, None)
              for i in range(60)]
    with patch.object(calibra, "coppie_complete", return_value=coppie):
        assert calibra.rapporto() == 0
    fuori = capsys.readouterr().out
    assert "Pearson" in fuori and "banda" in fuori, \
        "il coefficiente deve uscire con la sua banda, come nel frontend"
    assert "LITIGANO" in fuori


# ── Il confronto fra i due prompt ─────────────────────────────────────────
#
# Il prompt di produzione, misurato su 300 articoli, dava media +0.254 contro
# il -0.008 del tono GDELT. Su titoli finanziari presi a caso una media cosi'
# afferma che le notizie sono sistematicamente buone.
def test_il_prompt_bilanciato_scrive_nella_terza_colonna():
    pool, conn, cur = _pool()
    with patch("database.get_pool", return_value=pool), \
         patch("sentiment_groq.score_batch", return_value=[0.1, 0.0, -0.1]) as sb:
        calibra.valuta(RIGHE, scrivi=True, bilanciato=True)

    scritture = " ".join(str(c) for c in cur.executemany.call_args_list)
    assert "sentiment_3" in scritture
    assert "sentiment_2" not in scritture, "ha sovrascritto il primo parere"
    assert sb.call_args.kwargs["prompt"] is not None, "non ha usato il prompt nuovo"


def test_il_giro_normale_non_usa_il_prompt_in_prova():
    pool, _, _ = _pool()
    with patch("database.get_pool", return_value=pool), \
         patch("sentiment_groq.score_batch", return_value=[0.1, 0.0, -0.1]) as sb:
        calibra.valuta(RIGHE, scrivi=True)
    assert sb.call_args.kwargs["prompt"] is None


def test_scala_piu_stretta_ma_stesso_ordine_e_una_ricalibrazione(capsys):
    """
    Il nuovo dice le stesse cose su un righello piu' corto: l'ordine degli
    articoli e' identico, cambia solo l'ampiezza. Non si e' perso niente.
    """
    coppie = [("NVDA", f"t{i}", 0.0,
               0.25 + (i % 9) / 10,          # vecchio: spostato in positivo
               ((i % 9) / 10 - 0.4) * 0.6)   # nuovo: centrato, meta' scala, stesso ordine
              for i in range(60)]
    calibra._confronto_prompt(coppie)
    fuori = capsys.readouterr().out
    assert "è migliore" in fuori
    assert "Spearman" in fuori


def test_se_l_ordine_si_rimescola_non_e_una_ricalibrazione(capsys):
    """
    Media a zero ottenuta cambiando giudizio, non righello. Il vecchio criterio
    guardava solo la deviazione standard e qui avrebbe detto "migliore": e'
    esattamente l'errore per cui il confronto e' stato riscritto.
    """
    import random
    random.seed(3)
    vecchi = [0.25 + (i % 9) / 10 for i in range(60)]
    nuovi = [(i % 9) / 10 - 0.4 for i in range(60)]
    random.shuffle(nuovi)
    coppie = [("NVDA", f"t{i}", 0.0, v, nv)
              for i, (v, nv) in enumerate(zip(vecchi, nuovi))]
    calibra._confronto_prompt(coppie)
    fuori = capsys.readouterr().out
    assert "giudizio diverso" in fuori
    assert "SI CONTRADDICONO" in fuori


def test_senza_terza_colonna_dice_solo_come_ottenerla(capsys):
    coppie = [("NVDA", "t", 0.0, 0.3, None) for _ in range(60)]
    calibra._confronto_prompt(coppie)
    assert "--rivaluta" in capsys.readouterr().out


# ── I doppioni ────────────────────────────────────────────────────────────
#
# Dodici disaccordi su dodici fra i due prompt erano lo stesso articolo,
# "Intel targets $15 billion stock sale after rally", ripreso nove volte. E
# nella lista precedente la banca centrale russa compariva nove volte su venti.
# Trecento righe non sono trecento notizie.
def test_la_stessa_notizia_ripresa_altrove_conta_una_volta():
    righe = [("INTC", "Intel targets $15 billion stock sale after rally", 0, 0.4, -0.2),
             ("INTC", "Intel targets $15 billion stock sale after rally!", 0, 0.5, -0.2),
             ("INTC", "INTEL TARGETS $15 BILLION STOCK SALE AFTER RALLY", 0, 0.4, -0.2),
             ("NVDA", "Nvidia beats expectations", 0, 0.6, 0.4)]
    assert len(calibra._senza_doppioni(righe)) == 2


def test_titoli_diversi_restano_diversi():
    righe = [("INTC", "Intel targets stock sale", 0, 0.4, -0.2),
             ("INTC", "Intel seeks 15 billion as turnaround boosts shares", 0, 0.5, 0.1)]
    assert len(calibra._senza_doppioni(righe)) == 2


def test_il_censimento_dice_quante_sono_riprese(capsys):
    righe = [("INTC", "Stessa notizia di agenzia", 0, 0.4, -0.2)] * 9
    righe += [("NVDA", f"notizia diversa {i}", 0, 0.1, 0.1) for i in range(3)]
    calibra.censimento_doppioni(righe)
    fuori = capsys.readouterr().out
    assert "12" in fuori and "4" in fuori, "deve dire righe e notizie distinte"
    assert "9 volte" in fuori or "9  volte" in fuori.replace("  ", " ")


def test_il_confronto_fra_prompt_gira_sulle_notizie_distinte(capsys):
    """
    Con le riprese dentro, un solo lancio d'agenzia ripetuto pesa quanto tutte
    le altre notizie messe insieme, e il confronto misura la sindacazione
    invece dei due prompt.
    """
    righe = [("INTC", "Stessa notizia", 0.0, 0.5, -0.2)] * 50
    righe += [("NVDA", f"notizia {i}", 0.0, (i % 9) / 10, (i % 9) / 10 - 0.4)
              for i in range(40)]
    calibra._confronto_prompt(righe)
    fuori = capsys.readouterr().out
    assert "41 notizie distinte" in fuori
