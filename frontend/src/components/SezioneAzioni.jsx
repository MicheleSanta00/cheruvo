import Icon from './Icon.jsx'

/**
 * SezioneAzioni.jsx — La sezione titoli azionari, temporaneamente chiusa.
 *
 * Perché è chiusa davvero e non per finta. A luglio 2026 sono state staccate
 * NewsAPI, Google News RSS e i feed Yahoo perché nessuna di quelle licenze
 * consente l'uso commerciale. GDELT, l'unica fonte rimasta con licenza libera,
 * non indicizza abbastanza stampa finanziaria italiana: misurato il 4 agosto,
 * zero articoli su Eni, Enel, Intesa, UniCredit e STM in un'intera giornata.
 * Mostrare una sezione che promette trentaquattro titoli e ne copre nove
 * sarebbe peggio che non mostrarla.
 *
 * Il testo dice questo, per intero. Non "in manutenzione": una spiegazione
 * vera regge a qualsiasi domanda, e la scelta di rinunciare a fonti comode
 * per una questione di licenze racconta del prodotto più di quanto farebbe
 * una scusa generica.
 */
export default function SezioneAzioni({ onVaiACrypto, lang = 'it' }) {
  const it = lang === 'it'

  return (
    <div style={{
      flex: 1, display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
      padding: '48px 24px', overflowY: 'auto',
    }}>
      <div style={{ maxWidth: 620, width: '100%' }}>

        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 7,
          fontSize: 10, letterSpacing: '.14em', textTransform: 'uppercase',
          color: 'var(--azure)', fontWeight: 700, marginBottom: 14,
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%', background: 'var(--azure)',
          }} />
          {it ? 'Sezione in ricostruzione' : 'Section being rebuilt'}
        </div>

        <h2 style={{
          fontFamily: 'var(--serif)', fontSize: 30, fontWeight: 400,
          letterSpacing: '-.01em', marginBottom: 14, color: 'var(--white)',
        }}>
          {it ? 'L\'analisi dei titoli azionari torna quando sarà affidabile'
              : 'Stock analysis returns when it is reliable'}
        </h2>

        <p style={{ color: 'var(--muted)', fontSize: 14.5, lineHeight: 1.65, marginBottom: 14 }}>
          {it
            ? 'A luglio abbiamo staccato tre fonti di notizie perché le loro licenze non consentono l\'uso commerciale. Era la scelta giusta, ma ha lasciato scoperta la Borsa Italiana: le fonti rimaste con licenza libera non coprono abbastanza la stampa finanziaria italiana.'
            : 'In July we cut three news sources because their licences do not allow commercial use. It was the right call, but it left Italian equities uncovered: the remaining freely licensed sources do not index enough Italian financial press.'}
        </p>

        <p style={{ color: 'var(--muted)', fontSize: 14.5, lineHeight: 1.65, marginBottom: 22 }}>
          {it
            ? 'Preferiamo tenere chiusa questa sezione piuttosto che mostrare un sentiment costruito su troppe poche notizie. Stiamo lavorando con gli archivi ufficiali delle società quotate, quelli autorizzati da Consob, per riaprirla su dati di prima mano.'
            : 'We would rather keep this section closed than show a sentiment built on too few articles. We are working with the official filings archives of listed companies to reopen it on first-hand data.'}
        </p>

        {/* Cosa funziona ADESSO: la sezione chiusa non deve essere un vicolo
            cieco, deve portare da qualche parte. */}
        <div style={{
          border: '1px solid var(--border-br)', borderRadius: 8, overflow: 'hidden',
        }}>
          <div style={{
            padding: '8px 14px', background: 'var(--near-black)',
            borderBottom: '1px solid var(--border)',
            fontSize: 10, letterSpacing: '.12em', textTransform: 'uppercase',
            color: 'var(--muted)', fontWeight: 700,
          }}>
            {it ? 'Attivo adesso' : 'Live now'}
          </div>
          <div style={{ padding: '16px 14px' }}>
            <p style={{ fontSize: 14, lineHeight: 1.6, marginBottom: 14, color: 'var(--off-white)' }}>
              {it
                ? 'La sezione criptovalute è completa e aggiornata: sentiment sulle notizie, grafico della seduta che si muove ventiquattro ore su ventiquattro, e l\'indice di paura e avidità del mercato messo a confronto con il nostro.'
                : 'The crypto section is complete and live: news sentiment, an intraday chart that moves around the clock, and the market fear and greed index compared against ours.'}
            </p>
            <button onClick={onVaiACrypto} className="btn-glow" style={{
              display: 'inline-flex', alignItems: 'center', gap: 8,
              padding: '9px 16px', borderRadius: 7, fontSize: 13, fontWeight: 700,
              color: '#fff', border: 'none', cursor: 'pointer',
            }}>
              {it ? 'Vai alle criptovalute' : 'Go to crypto'}
              <Icon name="arrow-right" size={13} />
            </button>
          </div>
        </div>

        <p style={{ fontSize: 11.5, color: 'var(--faint, var(--muted))', marginTop: 18, lineHeight: 1.55 }}>
          {it
            ? 'Nessuna data promessa: dipende da risposte che non dipendono da noi. Quando riapre, riapre perché funziona.'
            : 'No promised date: it depends on answers that are not ours to give. When it reopens, it reopens because it works.'}
        </p>
      </div>
    </div>
  )
}
