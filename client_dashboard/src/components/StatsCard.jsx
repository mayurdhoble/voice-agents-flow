export default function StatsCard({ label, value, sub, accent }) {
  return (
    <div className="card-hover bg-white rounded-xl border border-gray-100 px-5 py-4 cursor-default">
      <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">{label}</p>
      <p className={`text-3xl font-bold mt-2 tabular-nums ${accent || 'text-gray-900'}`}>
        {value ?? '—'}
      </p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  )
}
