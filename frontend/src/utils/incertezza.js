/**
 * incertezza.js — I numeri che l'app mostra, con la banda che gli spetta.
 *
 * PERCHÉ ESISTE QUESTO FILE
 *
 * La correlazione era scritta tre volte: in Chart.jsx, in CorrelationPanel.jsx
 * e in generatePDF.js, con tre soglie diverse (5, 5 e 10) e tre scale di
 * aggettivi diverse. Tre copie della stessa formula sono tre occasioni perché
 * il difetto torni dopo essere stato tolto da una sola.
 *
 * Poi si è visto che lo stesso difetto viveva anche altrove, sotto forma di
 * medie di rendimento, quindi il file ha smesso di chiamarsi correlazione.js:
 * qui dentro ci va qualunque numero che l'interfaccia mostra a un utente e che
 * senza la sua incertezza sembra un fatto.
 *
 * IL DIFETTO CHE HA FATTO NASCERE IL FILE
 *
 * L'11 agosto 2026 un utente ha chiesto perché su NVDA la correlazione dicesse
 * -0.712. Andando a contare, era calcolata su CINQUE giorni. Di quei cinque uno
 * solo reggeva tutto il risultato, il 3 agosto, sentiment -0.30 con il titolo a
 * +4.53%:
 *
 *     su tutti e 5 i giorni       r = -0.737
 *     togliendo il 3 agosto       r = +0.244      <- cambia segno
 *     togliendo il 4 agosto       r = -0.736
 *     togliendo il 6 agosto       r = -0.682
 *     togliendo il 7 agosto       r = -0.846
 *     togliendo il 10 agosto      r = -0.934
 *
 * E su duecentomila coppie di serie CASUALI lunghe cinque, un |r| ≥ 0.737 esce
 * nel 15,5% dei casi: per vedere quel numero non serve che una relazione ci sia.
 * Nonostante questo il pannello lo stampava a tre decimali, grande, in rosso,
 * con scritto sotto "Forte negativa".
 *
 * QUANTO SERVE PER POTER DIRE QUALCOSA
 *
 * Larghezza della banda al 95% attorno a r = 0, al variare delle coppie:
 *
 *     coppie      banda            coppie      banda
 *          5    ± 0.88                 25    ± 0.40
 *         10    ± 0.63                 30    ± 0.36
 *         15    ± 0.51                 60    ± 0.25
 *         20    ± 0.44                 90    ± 0.21
 *
 * Sotto le venti coppie la banda è più larga di 0.44, cioè più larga di
 * qualunque relazione che avrebbe senso rivendicare fra sentiment e prezzo:
 * qualsiasi numero mostrato lì dentro è rumore travestito da misura. Da venti
 * in su il numero si può mostrare, ma sempre accanto alla sua banda.
 *
 * COSA È SPARITO
 *
 * Gli aggettivi "Forte" e "Moderata". Erano la parte che ingannava: davano un
 * giudizio di intensità a un numero che non era nemmeno distinguibile da zero.
 * Adesso o la banda esclude lo zero e allora si dice positiva o negativa, o non
 * lo esclude e allora si dice esattamente quello.
 */

export const MIN_COPPIE = 20

const round3 = (v) => parseFloat(v.toFixed(3))

/**
 * Correlazione di Pearson fra due serie, con la banda al 95%.
 *
 * Le due serie possono contenere buchi (null o undefined): vengono tenute solo
 * le posizioni in cui ci sono entrambi i valori, perché una coppia a metà non
 * è una coppia.
 *
 * Restituisce sempre un oggetto, mai null, così chi la usa non deve
 * distinguere fra "non calcolata" e "calcolata male": se `r` è null il motivo
 * sta in `n`.
 */
export function correlazione(xs, ys) {
  const coppie = []
  for (let i = 0; i < xs.length; i++) {
    const a = xs[i]
    const b = ys[i]
    if (a == null || b == null || Number.isNaN(a) || Number.isNaN(b)) continue
    coppie.push([Number(a), Number(b)])
  }

  const n = coppie.length
  if (n < MIN_COPPIE) return { r: null, n }

  const mx = coppie.reduce((s, [a]) => s + a, 0) / n
  const my = coppie.reduce((s, [, b]) => s + b, 0) / n
  let num = 0, dx = 0, dy = 0
  for (const [a, b] of coppie) {
    num += (a - mx) * (b - my)
    dx  += (a - mx) ** 2
    dy  += (b - my) ** 2
  }
  // Varianza nulla da una delle due parti: la correlazione non è definita.
  // Succede davvero, per esempio quando tutti i giorni hanno sentiment 0.
  if (!dx || !dy) return { r: null, n }

  const r = Math.max(-1, Math.min(1, num / Math.sqrt(dx * dy)))

  // Trasformazione di Fisher. La banda non si può prendere direttamente su r
  // perché r vive fra -1 e +1 e la sua distribuzione si storce vicino agli
  // estremi: a r = 0.9 c'è molto più spazio verso il basso che verso l'alto.
  // In atanh la distribuzione è circa normale con errore standard 1/√(n-3),
  // quindi la banda si calcola lì e si riporta indietro con tanh.
  const z  = Math.atanh(r)
  const se = 1 / Math.sqrt(n - 3)
  return {
    r: round3(r),
    n,
    lo: round3(Math.tanh(z - 1.96 * se)),
    hi: round3(Math.tanh(z + 1.96 * se)),
  }
}

/**
 * Media di una serie, con la banda al 95%.
 *
 * IL SECONDO POSTO IN CUI VIVEVA LO STESSO DIFETTO
 *
 * Il pannello correlazione mostra da sempre due riquadri: "rendimento medio
 * dopo i giorni bullish" e lo stesso per i bearish. Erano dietro il piano a
 * pagamento, colorati di verde o di rosso, e si leggevano come una regola
 * operativa. Il 11 agosto 2026 sono stati misurati su sei ticker:
 *
 *     NVDA    bullish    2 giorni   -0.30%   banda  -5.34 / +4.74
 *     NVDA    bearish    1 giorno   +2.56%   una giornata sola
 *     BTC     bullish    6 giorni   -0.21%   banda  -1.01 / +0.59
 *     BTC     bearish   12 giorni   +0.45%   banda  -0.35 / +1.25
 *     ETH     bullish   16 giorni   -0.26%   banda  -1.08 / +0.56
 *     ETH     bearish   17 giorni   +0.14%   banda  -0.74 / +1.02
 *     AAPL    bullish    3 giorni   -0.29%   banda  -1.60 / +1.02
 *     TSLA    bearish    2 giorni   +1.43%   banda  -2.61 / +5.47
 *     MSFT    bullish    1 giorno   +0.03%   una giornata sola
 *
 * Sette medie calcolabili su sette comprendono lo zero, e due erano la
 * variazione di UN giorno presentata come una media. Nessuno di questi numeri
 * distingueva un effetto dall'assenza di effetto.
 *
 * QUANTI GIORNI SERVONO DAVVERO
 *
 * La deviazione dei rendimenti giornalieri misurata su questi ticker sta fra
 * 1.0% e 3.6%, con mediana 1.7%. Da lì:
 *
 *     10 giorni  ->  banda ± 1.05%          45 giorni  ->  banda ± 0.50%
 *     20 giorni  ->  banda ± 0.75%          60 giorni  ->  banda ± 0.43%
 *     30 giorni  ->  banda ± 0.61%          90 giorni  ->  banda ± 0.35%
 *
 * Trenta è la soglia scelta, e non è una benedizione: a trenta giorni la banda
 * è ancora ± 0.61%, più larga di quasi ogni effetto che avrebbe senso
 * rivendicare. È il punto sotto il quale il numero non va nemmeno stampato.
 * Sopra, si stampa sempre insieme alla banda.
 */
export const MIN_GIORNI_MEDIA = 30

export function mediaConBanda(valori) {
  const v = (valori || [])
    .filter((x) => x != null && !Number.isNaN(Number(x)))
    .map(Number)
  const n = v.length
  if (n < MIN_GIORNI_MEDIA) return { media: null, n }

  const mu = v.reduce((s, x) => s + x, 0) / n
  const sd = Math.sqrt(v.reduce((s, x) => s + (x - mu) ** 2, 0) / (n - 1))
  const se = sd / Math.sqrt(n)
  return {
    media: round3(mu),
    n,
    dev: round3(sd),
    lo: round3(mu - 1.96 * se),
    hi: round3(mu + 1.96 * se),
  }
}

/**
 * Vero se i dati non distinguono questo numero da zero, cioè da "nessun
 * effetto". Comprende il caso in cui il numero non è stato proprio calcolato.
 *
 * Funziona sia sul risultato di `correlazione` sia su quello di
 * `mediaConBanda`: guarda la banda e non il valore, che è il punto.
 */
export function compatibileConZero(c) {
  if (!c || c.lo == null || c.hi == null) return true
  return c.lo <= 0 && c.hi >= 0
}

/** L'etichetta corta, senza aggettivi di intensità. */
export function etichetta(c) {
  if (!c || c.r == null) return 'Dati insufficienti'
  if (compatibileConZero(c)) return 'Non distinguibile da zero'
  return c.r > 0 ? 'Positiva' : 'Negativa'
}

/** La riga sotto al numero, quella che dice perché. */
export function spiegazione(c) {
  if (!c || c.r == null) {
    return `servono ${MIN_COPPIE} giorni, ne hai ${c?.n ?? 0}`
  }
  const seg = (v) => `${v > 0 ? '+' : ''}${v}`
  const banda = `banda ${seg(c.lo)} / ${seg(c.hi)}`
  return compatibileConZero(c)
    ? `${banda}: comprende lo zero`
    : `${banda} su ${c.n} giorni`
}
