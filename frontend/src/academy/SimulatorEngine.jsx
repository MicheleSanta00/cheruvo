/**
 * SimulatorEngine.jsx — cursori interattivi con calcolo live (serie o ripartizione).
 * Usa la libreria simModels.js. Riusato per giocare e per l'anteprima del workspace.
 */
import { useState } from 'react'
import { SIM_MODELS } from './simModels.js'
import { pick } from './academyStrings.js'

const eur = (n) => '€' + Math.round(n).toLocaleString('it-IT')

export default function SimulatorEngine({ content, lang = 'it', strings = {}, mode = 'play', onComplete }) {
  const model = SIM_MODELS[content && content.model]
  const [vals, setVals] = useState(() =>
    Object.fromEntries(((model && model.inputs) || []).map((i) => [i.key, i.def])))

  if (!model) return <div style={{ color: 'var(--muted)', fontSize: 13 }}>—</div>

  const out = model.compute(vals)
  const set = (k, val) => setVals((p) => ({ ...p, [k]: val }))

  return (
    <div>
      {model.inputs.map((inp) => (
        <div key={inp.key} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <label style={{ width: 110, fontSize: 13.5, color: 'var(--muted)' }}>{pick(inp.label, lang)}</label>
          <input type="range" min={inp.min} max={inp.max} step={inp.step} value={vals[inp.key]}
            onChange={(e) => set(inp.key, +e.target.value)} style={{ flex: 1, accentColor: '#34d399' }} />
          <span style={{ width: 90, textAlign: 'right', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
            {inp.unit === '€' ? eur(vals[inp.key]) : vals[inp.key] + (inp.unit ? ' ' + inp.unit : '')}
          </span>
        </div>
      ))}

      {out.kind === 'series' && (
        <>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, margin: '14px 0 10px' }}>
            <span style={{ fontSize: 14, color: 'var(--muted)' }}>{pick(out.resultLabel, lang)}</span>
            <span style={{ fontSize: 26, fontWeight: 700, color: '#34d399' }}>{eur(out.value)}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 120, padding: 10,
            borderRadius: 10, background: 'var(--black)', border: '1px solid var(--border)' }}>
            {out.series.map((val, i) => {
              const max = Math.max(...out.series, out.value) || 1
              return <div key={i} title={eur(val)} style={{ flex: 1, minHeight: 2,
                height: Math.max(2, (val / max) * 100) + '%', background: '#34d399', opacity: 0.85, borderRadius: '2px 2px 0 0' }} />
            })}
          </div>
        </>
      )}

      {out.kind === 'breakdown' && (
        <div style={{ marginTop: 14, display: 'grid', gap: 10 }}>
          {out.items.map((it, i) => (
            <div key={i}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13.5, marginBottom: 4 }}>
                <span style={{ color: 'var(--muted)' }}>{pick(it.label, lang)}</span>
                <span style={{ fontWeight: 600 }}>{eur(it.value)}</span>
              </div>
              <div style={{ height: 8, borderRadius: 99, background: 'var(--black)', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: '100%', background: it.color, opacity: 0.85 }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {content.teach && (pick(content.teach, lang)) && (
        <div style={{ display: 'flex', gap: 10, marginTop: 14, background: 'rgba(106,166,255,0.08)',
          border: '1px solid rgba(106,166,255,0.2)', borderRadius: 10, padding: '11px 13px', fontSize: 13.5, color: '#c9dbff' }}>
          💡 <div>{pick(content.teach, lang)}</div>
        </div>
      )}

      {mode === 'play' && (
        <button onClick={() => onComplete && onComplete({ correct: 0 })} style={{
          marginTop: 16, border: 'none', borderRadius: 10, padding: '11px 18px', cursor: 'pointer',
          fontSize: 14, fontWeight: 600, background: '#34d399', color: '#04221a' }}>
          {strings.backToPaths || 'Completa'}
        </button>
      )}
    </div>
  )
}
