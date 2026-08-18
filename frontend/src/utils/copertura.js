/**
 * copertura.js — Dire quanto c'e' dietro un titolo PRIMA che uno ci clicchi.
 *
 * PERCHE' ESISTE
 *
 * Il selettore offre 302 titoli. L'archivio ne raccoglie di continuo 52, e il
 * 18 agosto 2026 solo 27 arrivavano a cinque notizie distinte in 48 ore. Chi
 * apriva la lista e sceglieva un nome a caso aveva meno di una probabilita'
 * su dieci di trovarci qualcosa, e nessun modo di saperlo prima.
 *
 * Il 17 agosto la sessione piu' attiva mai registrata ha scritto a mano ADIL
 * e BB, che nella lista non ci sono nemmeno, e ha premuto scarica.
 *
 * Era l'unico punto del prodotto che prometteva senza dire quanto: la
 * correlazione si rifiuta di comparire sotto i venti giorni, il rilevatore di
 * anomalie dichiara "in apprendimento", i giorni senza notizie restano vuoti
 * invece di diventare zeri. Qui no.
 *
 * QUATTRO STATI, E "NON LO SO" E' UNO DI QUELLI
 *
 *   ignoto   la copertura non e' ancora arrivata dal backend. NON si mostra
 *            niente: un "0 notizie" mentre il dato e' in volo e' una bugia
 *            che dura un secondo, e nel selettore un secondo basta a far
 *            scartare un titolo che invece ne ha novanta.
 *   vuota    nessuna notizia in archivio negli ultimi giorni.
 *   scarsa   qualcosa c'e', ma sotto la soglia della classifica: la media si
 *            puo' leggere, la posizione in classifica no.
 *   piena    almeno `min_news` notizie distinte nella finestra.
 *
 * I conteggi sono quelli della classifica, riprese fuse, perche' vengono
 * dalla stessa query: vedi CHIAVE_TITOLO_SQL in market.py.
 */

export const IGNOTO = 'ignoto'
export const VUOTA = 'vuota'
export const SCARSA = 'scarsa'
export const PIENA = 'piena'

/**
 * Quanto c'e' dietro `ticker`, secondo la risposta di /market/copertura.
 * `copertura` null o non ancora caricata vuol dire IGNOTO, mai VUOTA.
 */
export function statoCopertura(copertura, ticker) {
  if (!copertura || !copertura.titoli) {
    return { stato: IGNOTO, ora: null, settimana: null, minNews: null }
  }
  const minNews = copertura.min_news ?? 5
  const v = copertura.titoli[ticker]
  if (!v || (!v.ora && !v.settimana)) {
    return { stato: VUOTA, ora: 0, settimana: 0, minNews }
  }
  return {
    stato: v.ora >= minNews ? PIENA : SCARSA,
    ora: v.ora ?? 0,
    settimana: v.settimana ?? 0,
    minNews,
  }
}

/**
 * La riga da mostrare accanto al nome. Stringa vuota quando non si sa: chi
 * chiama non deve inventarsi un trattino.
 */
export function etichettaCopertura(c, lang = 'it') {
  const it = lang === 'it'
  switch (c.stato) {
    case IGNOTO:
      return ''
    case VUOTA:
      return it ? 'nessuna notizia in archivio' : 'no news in archive'
    case SCARSA:
      // Il numero dei sette giorni, non quello delle 48 ore: se in due giorni
      // ce ne sono zero ma nella settimana nove, dire "0 notizie" fa
      // scartare un titolo su cui c'e' qualcosa da leggere.
      return it
        ? `${c.settimana} ${c.settimana === 1 ? 'notizia' : 'notizie'} in 7 giorni`
        : `${c.settimana} ${c.settimana === 1 ? 'story' : 'stories'} in 7 days`
    case PIENA:
      return it
        ? `${c.ora} ${c.ora === 1 ? 'notizia' : 'notizie'} in 48 ore`
        : `${c.ora} ${c.ora === 1 ? 'story' : 'stories'} in 48h`
    default:
      return ''
  }
}

/**
 * Il colore della pastiglia. Non e' decorazione: e' l'unica cosa che si legge
 * scorrendo un elenco di sei voci senza fermarsi a leggere i numeri.
 */
export function coloreCopertura(stato) {
  if (stato === PIENA) return 'var(--green)'
  if (stato === SCARSA) return 'var(--muted)'
  if (stato === VUOTA) return 'var(--muted)'
  return 'transparent'
}

/**
 * Se su questo titolo ha senso proporre lo scarico su richiesta invece di
 * mostrare una pagina vuota. Solo a copertura NOTA e davvero vuota: mentre il
 * dato e' in volo non si propone niente.
 */
export function offriScarico(c) {
  return c.stato === VUOTA
}
