import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

const PIE_COLORS = ['#1e5cff', '#60a5fa', '#34d399', '#f87171', '#a78bfa', '#fb923c', '#38bdf8', '#e879f9']

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: 'var(--dark)', border: '1px solid var(--border-br)', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
      {payload[0].name && <div style={{ color: 'var(--muted)' }}>{payload[0].name}</div>}
      <div style={{ color: 'var(--azure)', fontWeight: 500 }}>{payload[0].value}</div>
    </div>
  )
}

export default function Stats({ news }) {
  if (!news.length) return null

  const sourceCounts = {}
  news.forEach(n => { sourceCounts[n.source] = (sourceCounts[n.source] || 0) + 1 })
  const pieData = Object.entries(sourceCounts)
    .sort((a, b) => b[1] - a[1]).slice(0, 8)
    .map(([name, value]) => ({ name, value }))

  const buckets = Array.from({ length: 20 }, (_, i) => ({
    range: (-1 + i * 0.1).toFixed(1),
    count: 0,
  }))
  news.forEach(n => {
    const idx = Math.min(19, Math.floor((n.sentiment + 1) / 0.1))
    if (buckets[idx]) buckets[idx].count++
  })

  return (
    <div>
      <h3 style={{ fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 400, letterSpacing: '-0.02em', marginBottom: 20 }}>
        Analytics
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 20 }}>

        {/* Source distribution */}
        <div style={{ background: 'rgba(var(--rgb-contrasto), 0.02)', border: '1px solid var(--border)', borderRadius: 12, padding: 20 }}>
          <div style={{ fontSize: 12, color: 'var(--muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 16 }}>Source distribution</div>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={90}
                dataKey="value" nameKey="name" paddingAngle={2}>
                {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} opacity={0.85}/>)}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 14px', marginTop: 8 }}>
            {pieData.map((d, i) => (
              <span key={i} style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: PIE_COLORS[i % PIE_COLORS.length], display: 'inline-block' }}/>
                {d.name}
              </span>
            ))}
          </div>
        </div>

        {/* Sentiment histogram */}
        <div style={{ background: 'rgba(var(--rgb-contrasto), 0.02)', border: '1px solid var(--border)', borderRadius: 12, padding: 20 }}>
          <div style={{ fontSize: 12, color: 'var(--muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 16 }}>Sentiment distribution</div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={buckets} barSize={12}>
              <XAxis dataKey="range" tick={{ fontSize: 9, fill: 'var(--muted)' }} interval={4} axisLine={false} tickLine={false}/>
              <YAxis tick={{ fontSize: 10, fill: 'var(--muted)' }} axisLine={false} tickLine={false}/>
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="count" radius={[3,3,0,0]}>
                {buckets.map((b, i) => (
                  <Cell key={i} fill={parseFloat(b.range) < 0 ? 'var(--red)' : parseFloat(b.range) < 0.1 ? 'var(--giallo)' : 'var(--green)'} opacity={0.75}/>
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

      </div>
    </div>
  )
}
