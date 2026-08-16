"""
Test del lettore dei file grezzi di GDELT.

Il rischio principale qui non è che il codice si rompa: è che conti troppo.
I file grezzi contengono TUTTO quello che GDELT vede nel mondo, meteo e sport
compresi, e undici dei nostri termini di ricerca sono anche parole comuni.
Senza filtro, "Avalanche kills three skiers" diventerebbe una notizia su AVAX
e il conteggio direbbe che la nuova fonte rende benissimo mentre in realtà
starebbe raccogliendo cronaca di montagna.
"""
import gdelt_grezzo as gg
from gdelt_source import TERMINE_QUERY, e_crypto


CRYPTO = {t: q for t, q in TERMINE_QUERY.items() if e_crypto(t)}
AZIONI = {t: q for t, q in TERMINE_QUERY.items() if not e_crypto(t)}


def _riga(titolo, dominio="esempio.com", tono=0.5, lingua_src=None):
    """Una riga GKG 2.1 finta, con le sue 27 colonne."""
    c = [""] * 27
    c[gg.COL_DATA] = "20260806180000"
    c[gg.COL_DOMINIO] = dominio
    c[gg.COL_URL] = f"http://{dominio}/x"
    c[gg.COL_TONO] = f"{tono},3.1,1.2,4.3,20,10,300"
    if lingua_src:
        c[gg.COL_TRADUZIONE] = f"srclc:{lingua_src};eng:Moses"
    if titolo:
        c[gg.COL_EXTRA] = f"<PAGE_TITLE>{titolo}</PAGE_TITLE>"
    return c


def _trovati(titolo):
    r = [_riga(titolo)]
    c, _, _ = gg.conta_pertinenti(r, CRYPTO)
    a, _, _ = gg.conta_pertinenti(r, AZIONI)
    return dict(c) | dict(a)


# ── Lettura del formato ───────────────────────────────────────────────────
def test_legge_titolo_tono_e_lingua():
    r = _riga("Bitcoin sale ancora", dominio="ilsole24ore.com",
              tono=2.7, lingua_src="ita")
    assert gg.titolo(r) == "Bitcoin sale ancora"
    assert gg.tono(r) == 2.7
    assert gg.lingua(r) == "ita"


def test_una_riga_senza_titolo_non_esplode():
    """Molte righe del GKG non hanno il titolo: vanno saltate, non contate."""
    r = _riga(None)
    assert gg.titolo(r) == ""
    assert _trovati("") == {}


def test_una_riga_troppo_corta_non_esplode():
    """
    Se GDELT cambiasse il numero di colonne, leggere per indice solleverebbe
    IndexError a metà di un file da decine di migliaia di righe.
    """
    corta = ["a", "b", "c"]
    assert gg.titolo(corta) == ""
    assert gg.tono(corta) is None
    assert gg.lingua(corta) == "eng"


def test_senza_info_di_traduzione_la_lingua_e_inglese():
    """Il feed inglese non porta il campo: l'assenza significa inglese."""
    assert gg.lingua(_riga("Bitcoin rallies")) == "eng"


# ── Il filtro contro i falsi positivi ─────────────────────────────────────
def test_scarta_le_parole_comuni_fuori_contesto():
    """
    Il caso che rende inutile la misura se non gestito: undici termini su
    trentuno sono anche parole di uso corrente.
    """
    assert _trovati("Avalanche kills three skiers in the Alps") == {}
    assert _trovati("Apple harvest hit by drought in Trentino") == {}
    assert _trovati("Amazon rainforest fires reach record levels") == {}
    assert _trovati("Stellar performance by the Italian swim team") == {}
    assert _trovati("Shell found on the beach sparks curiosity") == {}
    assert _trovati("Optimism grows ahead of the peace talks") == {}


def test_tiene_le_stesse_parole_quando_il_contesto_e_finanziario():
    assert _trovati("Avalanche price jumps 12% as AVAX token rallies") == {"AVAX-USD": 1}
    assert _trovati("Apple shares hit new high after earnings") == {"AAPL": 1}
    assert _trovati("Optimism token leads layer-2 market gains") == {"OP-USD": 1}


def test_le_sigle_rispettano_le_maiuscole():
    """
    "Stocks near record highs as traders wait" contiene due parole di contesto
    finanziario, quindi il filtro sul contesto da solo lo lascerebbe passare.
    L'unica cosa che separa la moneta dalla preposizione sono le maiuscole.
    """
    assert _trovati("Stocks near record highs as traders wait") == {}
    assert _trovati("NEAR crypto surges on protocol upgrade") == {"NEAR-USD": 1}


def test_il_contesto_funziona_anche_in_italiano():
    """
    Il feed tradotto è metà del valore dell'operazione: se le parole di
    contesto fossero solo inglesi, tutta la stampa italiana verrebbe scartata
    proprio mentre si va a cercarla.
    """
    assert _trovati("Bitcoin torna sopra i 100mila dollari in borsa") == {"BTC-USD": 1}
    assert _trovati("Enel, l'azione sale dopo i conti trimestrali") == {"ENEL.MI": 1}


def test_i_termini_non_ambigui_non_chiedono_contesto():
    """Bitcoin non ha omonimi: pretendere contesto perderebbe notizie vere."""
    assert _trovati("Bitcoin hits new record") == {"BTC-USD": 1}
    assert _trovati("Ethereum devs delay the upgrade again") == {"ETH-USD": 1}


def test_la_regola_del_contesto_e_quella_dichiarata():
    """
    Tre casi, tre motivi diversi. Se qualcuno un giorno cambia questa regola
    per alzare i numeri, è qui che il test deve fermarlo.
    """
    # Azienda: nome non ambiguo, ma "Google" compare in mezzo mondo di
    # notizie che col titolo azionario non c'entrano niente.
    assert gg.serve_contesto("GOOGL", "Google") is True
    # Moneta: il nome è già di per sé un termine di mercato.
    assert gg.serve_contesto("BTC-USD", "Bitcoin") is False
    # Moneta con un omonimo nel mondo reale.
    assert gg.serve_contesto("AVAX-USD", "Avalanche") is True


def test_le_azioni_senza_contesto_finanziario_restano_fuori():
    """
    Il difetto misurato il 7 agosto 2026: GOOGL e MSFT facevano 816 righe su
    1.541 raccolte in un giorno, quasi tutte aggiornamenti di prodotto.
    """
    assert _trovati("Google Maps adds lane guidance in Italy") == {}
    assert _trovati("Microsoft Teams down for thousands of users") == {}
    assert _trovati("Google shares rise after earnings beat") == {"GOOGL": 1}


def test_un_articolo_puo_valere_per_due_titoli():
    """
    Prima ci si fermava al primo che combaciava, e le azioni vengono prima
    delle monete nel dizionario: le cripto perdevano ogni articolo condiviso.
    """
    r = [_riga("Microsoft adds Bitcoin to its treasury, shares rise")]
    trovati, _, _ = gg.conta_pertinenti(r, TERMINE_QUERY)
    assert dict(trovati) == {"MSFT": 1, "BTC-USD": 1}


def test_i_confini_di_parola_reggono():
    """Senza confini, XRP prenderebbe XRPL e ogni sigla che lo contiene."""
    assert _trovati("XRPL ledger update ships") == {}


def test_la_versione_ingenua_conta_di_piu():
    """
    Il confronto fra i due conteggi è il numero che dice quanto rumore
    produrrebbe una raccolta senza filtro. Serve nel resoconto, quindi deve
    restare possibile chiederlo.
    """
    righe = [_riga("Avalanche kills three skiers in the Alps")]
    rigoroso, _, _ = gg.conta_pertinenti(righe, CRYPTO, rigoroso=True)
    ingenuo, _, _ = gg.conta_pertinenti(righe, CRYPTO, rigoroso=False)
    assert sum(rigoroso.values()) == 0
    assert sum(ingenuo.values()) == 1


# ── Il resoconto non deve rompersi sui casi limite ────────────────────────
def test_descrivi_formato_regge_un_file_vuoto(capsys):
    gg.descrivi_formato([])
    assert "vuoto" in capsys.readouterr().out


# ── Le azioni candidate ───────────────────────────────────────────────────
#
# L'11 agosto 2026: l'interfaccia offre 302 titoli, su GDELT se ne cercano 41.
# Gli altri hanno il grafico dei prezzi e nessuna notizia, per sempre.
def test_le_candidate_azioni_non_sono_gia_seguite():
    """Misurare una che si raccoglie gia' non dice niente di nuovo."""
    gia = set(TERMINE_QUERY) & set(gg.CANDIDATI_AZIONI)
    assert not gia, f"gia' seguite, vanno tolte dalle candidate: {sorted(gia)}"


def test_ogni_candidata_dichiara_una_previsione():
    """
    La previsione si scrive PRIMA della misura. Se una data per sicura si
    rivela sporca, l'errore deve restare scritto invece di essere riscritto
    dopo aver visto i numeri.
    """
    for tk, (nome, previsione) in gg.CANDIDATI_AZIONI.items():
        assert nome and previsione, tk
        assert len(previsione) > 5, f"{tk}: previsione troppo vaga"


def test_le_ambigue_sono_dichiarate_tali():
    """
    Questi nomi sono parole comuni o persone famose: Visa e' il visto
    d'ingresso, Leonardo e' da Vinci e DiCaprio, Generali in italiano vuol dire
    generals, Oracle e' l'oracolo di Omaha. Se qualcuno le promuove a "sicuro"
    senza misurarle, il test si accende.
    """
    for tk in ("V", "LDO.MI", "G.MI", "ORCL"):
        _, previsione = gg.CANDIDATI_AZIONI[tk]
        assert "ambiguo" in previsione.lower(), f"{tk} non e' dichiarata ambigua"


def test_la_misura_sceglie_l_elenco_giusto():
    """Il flag azioni deve cambiare l'insieme misurato, non solo il titolo."""
    import inspect
    sorgente = inspect.getsource(gg.misura_candidati)
    assert "CANDIDATI_AZIONI if azioni else CANDIDATI" in sorgente


# ── L'eccezione al filtro di contesto ─────────────────────────────────────
#
# Misurando le azioni candidate l'11 agosto 2026 e' saltato fuori che il filtro
# non colpisce a caso: TSMC in sei ore aveva zero righe utilizzabili e
# trentaquattro scartate, fra cui "Sony, TSMC confirm deal to set up smartphone
# camera chip venture in Japan". Il suffisso "-USD" veniva usato come se fosse
# una misura di ambiguita', e non lo e'.
def test_l_elenco_resta_vuoto_finche_la_misura_non_basta():
    """
    Il 15 agosto 2026 `--modo contesto` ha girato su 24 ore vere e sembrava
    dare una risposta: Nvidia 72 bocciate, AMD 69, e gli esempi mostrati
    erano notizie finanziarie vere.

    Sono stati aggiunti, e i test di `ingest_grezzo` hanno mostrato cosa
    entrava insieme: le note di rilascio dei driver RTX e le schede prodotto
    delle motherboard. Il resoconto stampa TRE esempi per titolo, e tre
    esempi non descrivono settantadue righe.

    Se questo test si accende, la domanda da farsi non e' "quale nome
    aggiungo" ma "ho contato quante bocciate sono prodotto e quante
    mercato", che e' la misura che ancora manca.
    """
    assert gg.NOMI_NETTI == set(), (
        "NOMI_NETTI non e' piu' vuoto: serve il conteggio prodotto/mercato "
        "per nome, non tre esempi presi dalla cima dell'elenco"
    )


def test_i_nomi_rumorosi_non_ci_sono_finiti_dentro():
    """
    Amazon aveva 163 bocciature ed erano liste di vestiti, Meta 131 col
    "meta" di Rainbow Six, Ferrari 48 di Formula 1. Numeri alti, ma di
    rumore: sono esattamente i nomi che il filtro deve continuare a coprire.
    """
    for termine in ("Amazon", "Meta", "Ferrari", "Google", "Apple",
                    "Intesa", "Santander", "Boeing", "Airbus"):
        assert termine not in gg.NOMI_NETTI, termine


def test_i_chip_non_sono_nomi_netti():
    """
    Sembravano i candidati migliori e sono i peggiori: "Nvidia" sta in ogni
    driver, "AMD" in ogni scheda madre, "Micron" in ogni banco di memoria.
    """
    for tk, termine in (("NVDA", "Nvidia"), ("AMD", "AMD"), ("MU", "Micron")):
        assert gg.serve_contesto(tk, termine) is True, termine


def test_un_nome_netto_non_chiede_piu_il_contesto(monkeypatch):
    monkeypatch.setattr(gg, "NOMI_NETTI", {"TSMC"})
    assert gg.serve_contesto("TSM", "TSMC") is False


def test_gli_altri_titoli_continuano_a_chiederlo(monkeypatch):
    monkeypatch.setattr(gg, "NOMI_NETTI", {"TSMC"})
    assert gg.serve_contesto("NVDA", "Nvidia") is True
    assert gg.serve_contesto("MSFT", "Microsoft") is True


def test_le_monete_restano_libere_come_prima(monkeypatch):
    monkeypatch.setattr(gg, "NOMI_NETTI", {"TSMC"})
    assert gg.serve_contesto("BTC-USD", "Bitcoin") is False


def test_ambigui_vince_su_nomi_netti(monkeypatch):
    """
    Se un nome finisce per sbaglio in tutti e due gli elenchi, deve
    sopravvivere la scelta prudente. Allentare questo filtro e' esattamente
    come il 7 agosto sono entrate 816 righe di spazzatura su 1.541.
    """
    monkeypatch.setattr(gg, "NOMI_NETTI", {"Apple", "Avalanche"})
    assert gg.serve_contesto("AAPL", "Apple") is True
    assert gg.serve_contesto("AVAX-USD", "Avalanche") is True


# ── Il vocabolario italiano di mercato ────────────────────────────────────
#
# La misura da 24 ore dell'11 agosto 2026 ha scartato dei resoconti di seduta
# italiani perche' CONTESTO non conosceva "Piazza Affari", cioe' il modo piu'
# comune con cui la stampa italiana chiama la Borsa di Milano.
def test_piazza_affari_e_un_contesto_finanziario():
    assert gg.CONTESTO.search(
        "Comparto chip tonico, a Piazza Affari gli acquisti premiano Prysmian +2,8%")


def test_le_altre_parole_aggiunte_funzionano():
    for t in ("Seduta borsistica in rialzo per Eni",
              "Enel annuncia un buyback da 2 miliardi",
              "Intesa Sanpaolo, riacquisto di azioni proprie",
              "Ferrari supera i 90 miliardi di capitalizzazione",
              "Eni colloca un'obbligazione da un miliardo"):
        assert gg.CONTESTO.search(t), t


def test_le_parole_ambigue_sono_state_lasciate_fuori():
    """
    "seduta" da sola e' anche quella parlamentare, "listino" e' anche il
    listino prezzi di un negozio. Allentare CONTESTO e' il modo piu' rapido di
    riempire l'archivio: nella raccolta del 7 agosto 2026 bastavano due nomi
    per portare dentro 816 righe di spazzatura su 1.541.
    """
    for t in ("Seduta fiume in consiglio comunale a Bergamo",
              "Il nuovo listino prezzi del ristorante fa discutere"):
        assert not gg.CONTESTO.search(t), t


# ── Le nove azioni adottate il 15 agosto 2026 ─────────────────────────────
#
# Escono dalla misura su 24 ore di file GDELT (318.782 righe). Il numero e'
# quante ne porterebbero al giorno DOPO il filtro di contesto.
NUOVE = {
    "JPM": ("JPMorgan", 24), "PLTR": ("Palantir", 18), "SAN.MC": ("Santander", 17),
    "BA": ("Boeing", 14), "SMCI": ("Super Micro", 8), "HOOD": ("Robinhood", 6),
    "AIR.PA": ("Airbus", 5), "ABNB": ("Airbnb", 5), "AVGO": ("Broadcom", 5),
}


def test_le_nove_adottate_sono_cercate_col_termine_misurato():
    """
    Il termine deve essere quello su cui e' stata fatta la misura. Cambiarlo
    dopo, anche di poco, vuol dire che i numeri nel commento non valgono piu'.
    """
    from gdelt_source import TERMINE_QUERY
    for tk, (termine, _) in NUOVE.items():
        assert TERMINE_QUERY.get(tk) == termine, f"{tk}: termine cambiato"


def test_le_nuove_chiedono_tutte_il_contesto_finanziario():
    """
    Sono azioni, quindi il contesto resta obbligatorio. Se una finisce in
    NOMI_NETTI deve essere perche' `--modo contesto` ha mostrato che il filtro
    le sta rubando notizie vere, non perche' rendeva poco.
    """
    from gdelt_source import TERMINE_QUERY
    for tk, (termine, _) in NUOVE.items():
        assert gg.serve_contesto(tk, termine) is True, tk


def test_ogni_adottata_supera_la_soglia_della_classifica():
    """
    Sotto 5 al giorno un titolo non entra mai in classifica (market.py,
    MIN_NEWS) e aggiunge solo una pagina che mostra un conteggio.
    """
    for tk, (_, al_giorno) in NUOVE.items():
        assert al_giorno >= 5, f"{tk} non arriva alla soglia"


def test_le_bocciate_restano_bocciate():
    """
    Visa faceva 1 riga buona contro 176 di permessi di soggiorno, Leonardo 3
    contro 69 fra da Vinci e DiCaprio, Terna in spagnolo e' la rosa di
    candidati a una carica. Se ricompaiono, qualcuno le ha adottate guardando
    solo la resa.
    """
    from gdelt_source import TERMINE_QUERY
    for tk in ("V", "LDO.MI", "TRN.MI", "DIS", "PST.MI", "NFLX", "SIE.DE"):
        assert tk not in TERMINE_QUERY, f"{tk} adottata senza risolvere il suo problema"


# ── La simmetria fra utili e perdite ──────────────────────────────────────
#
# Il 15 agosto 2026, provando CONTESTO su coppie costruite apposta, e' venuto
# fuori che il filtro faceva passare "SAP meldet Gewinn" e bocciava "SAP
# meldet Verlust". Nell'elenco c'erano gewinn, beneficios, ganancias, lucro e
# utile netto, e nessuna parola per la perdita in nessuna lingua.
#
# Non era un buco di copertura: era uno sbilanciamento. Sulla stampa non
# inglese entrava la notizia buona e restava fuori quella cattiva, quindi la
# media del sentiment saliva per costruzione proprio sulla meta' europea
# dell'archivio, che e' la parte che ci distingue.
_COPPIE = [
    ("deu", "SAP meldet Gewinn im zweiten Quartal",
            "SAP meldet Verlust im zweiten Quartal"),
    ("spa", "Santander anuncia beneficios record",
            "Santander anuncia perdidas millonarias"),
    ("ita", "Eni chiude con un utile netto in crescita",
            "Eni chiude in perdita nel trimestre"),
    ("por", "Vale anuncia lucro no trimestre",
            "Vale anuncia prejuizo no trimestre"),
    ("fra", "Airbus annonce des benefices en hausse",
            "Airbus annonce des pertes nettes en hausse"),
]


def test_la_notizia_cattiva_entra_quanto_quella_buona():
    for lingua, buona, cattiva in _COPPIE:
        assert gg.CONTESTO.search(buona), f"{lingua}: persa la buona"
        assert gg.CONTESTO.search(cattiva), f"{lingua}: persa la cattiva"


# ── Le parole che mancavano, prese dalle bocciature vere ──────────────────
_BOCCIATI_IL_15_AGOSTO = [
    "Nvidia in talks to invest $3 billion in SB Energy",
    "Tiger Global cuts stakes in major tech firms, adds AMD and SpaceX",
    "Boeing reports 37 commercial aircraft orders and 51 deliveries for Jul-2026",
    "Solana Kurs heute bei 76 Dollar, waehrend 29 Prozent des Netzwerks",
    "YPF, Eni y XRG invertiran US$51.000 millones para exportar gas",
    # Rimaste fuori al primo giro, viste rilanciando la misura il 16 agosto
    "AMD raises $4.75bn in its biggest ever bond sale",
    "Alphabet made 100x on SpaceX, now Nvidia reveals $21 billion stake",
    "Solana Company Q2 Loss Hits $30.3 Million as SOL Treasury Suffers",
]


def test_le_notizie_perse_adesso_entrano():
    for t in _BOCCIATI_IL_15_AGOSTO:
        assert gg.CONTESTO.search(t), t


# Ogni parola aggiunta e' un rischio di falso positivo, e queste sono le
# frasi che l'aggiunta poteva far entrare per sbaglio. "Democracy is at
# stake in the election" e' passata davvero al primo tentativo.
_NON_SONO_NOTIZIE_DI_MERCATO = [
    "Police open an investigation into the fire",
    "Democracy is at stake in the election",
    "The future of the party is at stake in Ohio",
    "Judge orders the company to appear in court",
    "Ich besuche einen Deutschkurs in Berlin",
    "La Ferrari si ferma in mezzo alla strada",
    "Perdita di gas in una palazzina del centro",
    "Weight loss drug shows promise in new trial",
    "Rainbow Six Siege Season 3 adds drone racing",
    # "bond sale" da solo faceva entrare questa: e' il motivo per cui al suo
    # posto c'e' la raccolta di capitale con la cifra.
    "James Bond sale of memorabilia draws crowds in London",
    "Q2 report of the school year published by the ministry",
]


def test_le_parole_nuove_non_aprono_la_porta_alla_cronaca():
    for t in _NON_SONO_NOTIZIE_DI_MERCATO:
        assert not gg.CONTESTO.search(t), t


# ── La cache dei file GDELT ───────────────────────────────────────────────
#
# I file del GKG non cambiano piu' una volta pubblicati, ma il 16 agosto 2026
# le stesse 24 ore, quasi un giga, sono state scaricate tre volte in una sera.
def _riga_piena(titolo):
    r = [""] * 27
    r[gg.COL_DATA] = "20260815204500"
    r[gg.COL_DOMINIO] = "ilsole24ore.com"
    r[gg.COL_URL] = "http://esempio.it/x"
    r[gg.COL_TONO] = "2.7,3.1,1.2,4.3,20,10,300"
    r[gg.COL_TRADUZIONE] = "srclc:ita;eng:Moses"
    r[gg.COL_TEMI] = "ECON_STOCKMARKET;TAX_FNCACT"
    r[gg.COL_EXTRA] = f"<PAGE_TITLE>{titolo}</PAGE_TITLE><ALTRO>zzz</ALTRO>"
    r[20] = "colonna che nessuno legge"
    return r


def test_la_riga_ridotta_risponde_come_quella_intera():
    """
    La cache tiene solo le colonne che qualcuno legge. Se una funzione legge
    per indice, deve trovare le stesse cose al posto giusto.
    """
    intera = _riga_piena("Eni chiude in perdita, il titolo scende")
    ridotta = gg._ridotta(intera)
    assert len(ridotta) == len(intera)
    assert gg.titolo(ridotta) == gg.titolo(intera)
    assert gg.tono(ridotta) == gg.tono(intera)
    assert gg.lingua(ridotta) == gg.lingua(intera)
    assert ridotta[gg.COL_TEMI] == intera[gg.COL_TEMI]
    # e quello che non serve non viene tenuto
    assert ridotta[20] == ""


def test_scrittura_e_rilettura_non_cambiano_i_titoli(tmp_path, monkeypatch):
    """
    Il primo tentativo usava csv.writer con escapechar e il lettore senza:
    una barra rovescia tornava raddoppiata, le virgolette precedute da una
    barra, e un tab spezzava la riga in due. Tre titoli su quattro tornavano
    diversi da come erano partiti.
    """
    monkeypatch.setattr(gg, "cartella_cache", lambda: str(tmp_path))
    difficili = [
        "Titolo con \\ barra rovescia",
        'Titolo con "virgolette" dentro',
        "Titolo con | pipe e ; punto e virgola",
        "Bitcoin'de haftalik kayip yuzde 3'u asti",
        "Επιμένει η Apple: Ζητά προμήθεια έως 15%",
    ]
    gg._nella_cache("prova.gkg.csv", [gg._ridotta(_riga_piena(t)) for t in difficili])
    lette = gg._dalla_cache("prova.gkg.csv")
    assert lette is not None and len(lette) == len(difficili)
    assert [gg.titolo(r) for r in lette] == difficili


def test_un_tab_dentro_un_titolo_non_spezza_la_riga(tmp_path, monkeypatch):
    """Il GKG stesso non ammette tab nei campi: qui diventa uno spazio."""
    monkeypatch.setattr(gg, "cartella_cache", lambda: str(tmp_path))
    gg._nella_cache("t.gkg.csv", [gg._ridotta(_riga_piena("Titolo con\ttab"))])
    lette = gg._dalla_cache("t.gkg.csv")
    assert len(lette) == 1
    assert gg.titolo(lette[0]) == "Titolo con tab"


def test_una_cache_illeggibile_si_ributta_via(tmp_path, monkeypatch):
    """Un file monco non deve far fallire una misura da venti minuti."""
    monkeypatch.setattr(gg, "cartella_cache", lambda: str(tmp_path))
    rotto = tmp_path / "rotto.gkg.csv.tsv.gz"
    rotto.write_bytes(b"questo non e' un gzip")
    assert gg._dalla_cache("rotto.gkg.csv") is None
    assert not rotto.exists(), "il file rotto va rimosso, non lasciato li'"


def test_niente_file_parziali_se_la_scrittura_va_male(tmp_path, monkeypatch):
    """
    Si scrive a fianco e poi si rinomina: se il programma muore a meta' non
    resta un file monco che la volta dopo viene letto come se fosse buono.
    """
    monkeypatch.setattr(gg, "cartella_cache", lambda: str(tmp_path))
    gg._nella_cache("ok.gkg.csv", [gg._ridotta(_riga_piena("Titolo"))])
    rimasti = [f.name for f in tmp_path.iterdir()]
    assert rimasti == ["ok.gkg.csv.tsv.gz"], rimasti


def test_svuota_cache_conta_quello_che_toglie(tmp_path, monkeypatch):
    monkeypatch.setattr(gg, "cartella_cache", lambda: str(tmp_path))
    for i in range(3):
        gg._nella_cache(f"f{i}.gkg.csv", [gg._ridotta(_riga_piena("Titolo"))])
    assert gg.misura_cache()[0] == 3
    n, _ = gg.svuota_cache()
    assert n == 3 and gg.misura_cache()[0] == 0


def test_la_cache_tiene_tutto_quello_che_qualcuno_legge():
    """
    Se una colonna viene letta da qualche parte nel codice ma non e' fra
    quelle conservate, con la cache accesa quella misura vedrebbe zeri e
    sembrerebbe che GDELT abbia smesso di pubblicarla. Meglio una cache piu'
    grande di una che mente a un modo su sei.
    """
    lette_dal_codice = {gg.COL_DATA, gg.COL_DOMINIO, gg.COL_URL, gg.COL_TEMI,
                        gg.COL_ORGANIZZAZIONI, gg.COL_TONO, gg.COL_NOMI,
                        gg.COL_TRADUZIONE}
    mancanti = lette_dal_codice - set(gg.COLONNE_TENUTE)
    assert not mancanti, f"colonne lette ma non conservate: {sorted(mancanti)}"
    # COL_EXTRA e' trattata a parte: se ne tiene solo il PAGE_TITLE.
    assert gg.COL_EXTRA not in gg.COLONNE_TENUTE


def test_descrivi_formato_dice_le_stesse_cose_su_una_riga_dalla_cache(capsys):
    intera = _riga_piena("Eni chiude in perdita")
    gg.descrivi_formato([intera])
    da_intera = capsys.readouterr().out
    gg.descrivi_formato([gg._ridotta(intera)])
    da_ridotta = capsys.readouterr().out
    assert da_intera == da_ridotta
