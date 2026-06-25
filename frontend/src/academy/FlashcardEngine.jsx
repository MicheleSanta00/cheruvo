/**
 * FlashcardEngine.jsx — glossario a carte fronte/retro con ripasso (le carte
 * "da rivedere" tornano in coda). Riusato per giocare e per l'anteprima.
 */
import { useState } from 'react'
import { pick } from './academyStrings.js'

export default function FlashcardEngine({ content, lang = 'it', strings = {}, mode = 'play', onComplete }) {
  const deck = (content && content.deck) || []
  const [queue, setQueue] = useState(deck.map((_, i) => i))
  const [flip, setFlip] = useState(false)
  const [known, setKnown] = useState(0)
  const [done, setDone] = useState(false)

  if (!deck.length) return <div style={{ color: 'var(--muted)', fontSize: 13 }}>—</div>

  const reset = () => { setQueue(deck.map((_, i) => i)); setFlip(false); setKnown(0); setDone(false) }

  if (done || !queue.length) {
    return (
      <div style={{ textAlign: 'center', padding: '8px 0' }}>
        <div style={{ fontSize: 34 }}>🎉</div>
        <div style={{ fontSize: 18, fontWeight: 600, margin: '6px 0' }}>{strings.lessonDone}</div>
        <div style={{ color: 'var(--muted)', fontSize: 14 }}>{known}/{deck.length} · +{known * 20 + 50} {strings.xpEarned}</div>
        {mode === 'play'
          ? <button onClick={() => onComplete && onComplete({ correct: known })} style={primaryBtn}>{strings.backToPaths}</button>
          : <button onClick={reset} style={ghostBtn}>{strings.restart}</button>}
      </div>
    )
  }

  const card = deck[queue[0]]
  const known1 = () => { setKnown((k) => k + 1); setFlip(false); setQueue((q) => q.slice(1)) }
  const again = () => { setFlip(false); setQueue((q) => [...q.slice(1), q[0]]) }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--muted)', fontSize: 12, marginBottom: 10 }}>
        <span>{queue.length} {strings.cardsLeft}</span>
        <span>{known} ✓</span>
      </div>

      <div onClick={() => setFlip((f) => !f)} style={{ cursor: 'pointer', minHeight: 130, display: 'flex',
        flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', gap: 8,
        background: 'var(--black)', border: '1px solid var(--border)', borderRadius: 14, padding: 20 }}>
        {!flip ? (
          <>
            <div style={{ fontSize: 19, fontWeight: 600 }}>{pick(card.term, lang)}</div>
            <div style={{ fontSize: 12, color: 'var(--muted)' }}>{strings.flip}</div>
          </>
        ) : (
          <>
            <div style={{ fontSize: 15 }}>{pick(card.definition, lang)}</div>
            {card.example && pick(card.example, lang) && (
              <div style={{ fontSize: 13, color: 'var(--muted)', fontStyle: 'italic' }}>{pick(card.example, lang)}</div>
            )}
          </>
        )}
      </div>

      {flip && (
        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <button onClick={again} style={{ ...ghostBtn, marginTop: 0, flex: 1 }}>{strings.again}</button>
          <button onClick={known1} style={{ ...primaryBtn, marginTop: 0, flex: 1 }}>{strings.knew}</button>
        </div>
      )}
    </div>
  )
}

const primaryBtn = { marginTop: 16, border: 'none', borderRadius: 10, padding: '11px 18px', cursor: 'pointer', fontSize: 14, fontWeight: 600, background: '#34d399', color: '#04221a' }
const ghostBtn = { marginTop: 16, border: '1px solid var(--border)', borderRadius: 10, padding: '11px 18px', cursor: 'pointer', fontSize: 14, fontWeight: 600, background: 'transparent', color: 'var(--white)' }
