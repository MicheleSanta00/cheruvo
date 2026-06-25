/**
 * simModels.js — libreria dei modelli di simulatore (calcoli nel frontend).
 * Ogni modello: label, formato, input (cursori) e compute() che restituisce
 * { kind: 'series'|'breakdown', ... }. Aggiungere un modello = una voce qui.
 */
const range = (n) => Array.from({ length: Math.max(1, n) + 1 }, (_, i) => i)

export const SIM_MODELS = {
  compound_interest: {
    label: { it: 'Interesse composto', en: 'Compound interest' },
    inputs: [
      { key: 'capitale', label: { it: 'Capitale', en: 'Principal' }, min: 100, max: 50000, step: 100, def: 1000, unit: '€' },
      { key: 'tasso', label: { it: 'Tasso annuo', en: 'Annual rate' }, min: 0, max: 12, step: 0.5, def: 6, unit: '%' },
      { key: 'anni', label: { it: 'Anni', en: 'Years' }, min: 1, max: 40, step: 1, def: 20, unit: '' },
    ],
    compute: (v) => {
      const r = v.tasso / 100
      const series = range(v.anni).map((y) => v.capitale * Math.pow(1 + r, y))
      return { kind: 'series', value: v.capitale * Math.pow(1 + r, v.anni), series, resultLabel: { it: 'Valore finale', en: 'Final value' } }
    },
  },
  pac: {
    label: { it: 'Piano di accumulo (PAC)', en: 'Recurring investing' },
    inputs: [
      { key: 'mensile', label: { it: 'Versamento mensile', en: 'Monthly amount' }, min: 10, max: 2000, step: 10, def: 200, unit: '€' },
      { key: 'tasso', label: { it: 'Rendimento annuo', en: 'Annual return' }, min: 0, max: 12, step: 0.5, def: 6, unit: '%' },
      { key: 'anni', label: { it: 'Anni', en: 'Years' }, min: 1, max: 40, step: 1, def: 15, unit: '' },
    ],
    compute: (v) => {
      const r = v.tasso / 100 / 12
      const fvAt = (months) => (r === 0 ? v.mensile * months : v.mensile * ((Math.pow(1 + r, months) - 1) / r))
      const series = range(v.anni).map((y) => fvAt(y * 12))
      return { kind: 'series', value: fvAt(v.anni * 12), series, resultLabel: { it: 'Capitale accumulato', en: 'Total accumulated' } }
    },
  },
  inflation: {
    label: { it: 'Inflazione', en: 'Inflation' },
    inputs: [
      { key: 'importo', label: { it: 'Importo oggi', en: 'Amount today' }, min: 100, max: 100000, step: 100, def: 10000, unit: '€' },
      { key: 'inflazione', label: { it: 'Inflazione annua', en: 'Annual inflation' }, min: 0, max: 10, step: 0.5, def: 3, unit: '%' },
      { key: 'anni', label: { it: 'Anni', en: 'Years' }, min: 1, max: 40, step: 1, def: 20, unit: '' },
    ],
    compute: (v) => {
      const r = v.inflazione / 100
      const series = range(v.anni).map((y) => v.importo / Math.pow(1 + r, y))
      return { kind: 'series', value: v.importo / Math.pow(1 + r, v.anni), series, resultLabel: { it: 'Potere d\'acquisto reale', en: 'Real purchasing power' } }
    },
  },
  budget_50_30_20: {
    label: { it: 'Budget 50/30/20', en: '50/30/20 budget' },
    inputs: [
      { key: 'stipendio', label: { it: 'Stipendio mensile', en: 'Monthly income' }, min: 500, max: 10000, step: 50, def: 1800, unit: '€' },
    ],
    compute: (v) => ({
      kind: 'breakdown',
      items: [
        { label: { it: 'Necessità (50%)', en: 'Needs (50%)' }, value: v.stipendio * 0.5, color: '#34d399' },
        { label: { it: 'Sfizi (30%)', en: 'Wants (30%)' }, value: v.stipendio * 0.3, color: '#6aa6ff' },
        { label: { it: 'Risparmio (20%)', en: 'Savings (20%)' }, value: v.stipendio * 0.2, color: '#f5c451' },
      ],
    }),
  },
}
