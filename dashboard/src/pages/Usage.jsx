import { useEffect, useState, useCallback } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, ResponsiveContainer,
} from 'recharts'
import StatsCard from '../components/StatsCard'
import Pagination from '../components/Pagination'

const COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#3b82f6']

const SERVICE_LABELS = {
  gemini_live: 'Gemini Live',
  vobiz:       'VoBiz',
  openrouter:  'OpenRouter',
}

const SERVICE_COLORS = {
  gemini_live: '#6366f1',
  vobiz:       '#22c55e',
  openrouter:  '#f59e0b',
}

const CostTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow px-3 py-2 text-xs">
      <p className="text-gray-500 mb-0.5">{label}</p>
      <p className="font-semibold text-gray-900">${payload[0].value.toFixed(6)}</p>
    </div>
  )
}

function fmt(n, dec = 4) {
  if (n == null) return '—'
  return `$${Number(n).toFixed(dec)}`
}

function fmtSec(s) {
  if (s == null) return '—'
  const m = Math.floor(s / 60)
  const sec = Math.round(s % 60)
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}

export default function Usage() {
  const [summary, setSummary] = useState(null)
  const [rows, setRows]       = useState([])
  const [total, setTotal]     = useState(0)
  const [page, setPage]       = useState(1)
  const [pages, setPages]     = useState(1)
  const [service, setService] = useState('')

  useEffect(() => {
    fetch('/api/usage/summary').then(r => r.json()).then(setSummary).catch(console.error)
  }, [])

  const fetchRows = useCallback(() => {
    const params = new URLSearchParams({ page, limit: 20 })
    if (service) params.set('service', service)
    fetch(`/api/usage?${params}`)
      .then(r => r.json())
      .then(d => { setRows(d.data || []); setTotal(d.total || 0); setPages(d.pages || 1) })
      .catch(console.error)
  }, [page, service])

  useEffect(() => { fetchRows() }, [fetchRows])

  const geminiCost  = summary?.service_breakdown?.find(s => s.service === 'gemini_live')?.cost ?? 0
  const vobizCost   = summary?.service_breakdown?.find(s => s.service === 'vobiz')?.cost ?? 0
  const orCost      = summary?.service_breakdown?.find(s => s.service === 'openrouter')?.cost ?? 0

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-gray-900">Usage &amp; Billing</h1>
        <p className="text-sm text-gray-500 mt-0.5">AI and telephony cost tracking per call</p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatsCard label="Total Cost (USD)"   value={fmt(summary?.total_cost_usd, 4)} />
        <StatsCard label="Gemini Live"        value={fmt(geminiCost, 4)}              sub="gemini-2.0-flash-live-001" />
        <StatsCard label="VoBiz Telephony"    value={fmt(vobizCost, 4)}              sub={`${summary?.total_call_min ?? 0} min total`} />
        <StatsCard label="OpenRouter"         value={fmt(orCost, 4)}                 sub={`${(summary?.total_input_tokens ?? 0) + (summary?.total_output_tokens ?? 0)} tokens`} />
      </div>

      {/* Secondary info cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        <StatsCard label="Audio In (caller)"  value={`${summary?.total_audio_in_min ?? 0} min`}  sub="sent to Gemini" />
        <StatsCard label="Audio Out (agent)"  value={`${summary?.total_audio_out_min ?? 0} min`} sub="from Gemini" />
        <StatsCard label="VoBiz Call Minutes" value={`${summary?.total_call_min ?? 0} min`}       sub="total telephony" />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        {/* Daily cost trend */}
        <div className="bg-white rounded-xl border border-gray-100 p-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-1">Daily Cost</h2>
          <p className="text-xs text-gray-400 mb-4">Last 30 days (USD)</p>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={summary?.cost_trend || []} margin={{ top: 0, right: 0, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: '#94a3b8' }}
                tickFormatter={v => v.slice(5)}
                interval={4}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 10, fill: '#94a3b8' }}
                tickFormatter={v => `$${v.toFixed(3)}`}
                axisLine={false}
                tickLine={false}
                width={55}
              />
              <Tooltip content={<CostTooltip />} cursor={{ fill: '#f8fafc' }} />
              <Bar dataKey="cost" fill="#6366f1" radius={[3, 3, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Cost by service pie */}
        <div className="bg-white rounded-xl border border-gray-100 p-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-1">Cost by Service</h2>
          <p className="text-xs text-gray-400 mb-4">Total spend breakdown</p>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie
                data={summary?.service_breakdown || []}
                dataKey="cost"
                nameKey="service"
                cx="50%"
                cy="50%"
                innerRadius={48}
                outerRadius={72}
                paddingAngle={3}
              >
                {(summary?.service_breakdown || []).map((d, i) => (
                  <Cell key={i} fill={SERVICE_COLORS[d.service] || COLORS[i % COLORS.length]} strokeWidth={0} />
                ))}
              </Pie>
              <Tooltip
                formatter={(v, name) => [`$${Number(v).toFixed(6)}`, SERVICE_LABELS[name] || name]}
                contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-3 mt-2">
            {(summary?.service_breakdown || []).map((d, i) => (
              <span key={i} className="flex items-center gap-1.5 text-xs text-gray-600">
                <span className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ background: SERVICE_COLORS[d.service] || COLORS[i % COLORS.length] }} />
                {SERVICE_LABELS[d.service] || d.service} — ${Number(d.cost).toFixed(4)} ({d.count} calls)
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Per-call log table */}
      <div className="bg-white rounded-xl border border-gray-100">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Usage Logs</h2>
            <p className="text-xs text-gray-400 mt-0.5">{total} records</p>
          </div>
          <select
            value={service}
            onChange={e => { setService(e.target.value); setPage(1) }}
            className="border border-gray-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">All services</option>
            <option value="gemini_live">Gemini Live</option>
            <option value="vobiz">VoBiz</option>
            <option value="openrouter">OpenRouter</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Service</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Model</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Audio In</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Audio Out</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Tokens In</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Tokens Out</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Duration</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Cost (USD)</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Time</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={9} className="px-6 py-10 text-center text-gray-400">No usage logs yet</td></tr>
              )}
              {rows.map(r => (
                <tr key={r.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50 transition-colors">
                  <td className="px-6 py-3.5">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium"
                      style={{
                        background: (SERVICE_COLORS[r.service] || '#e5e7eb') + '1a',
                        color: SERVICE_COLORS[r.service] || '#374151',
                      }}>
                      {SERVICE_LABELS[r.service] || r.service}
                    </span>
                  </td>
                  <td className="px-6 py-3.5 text-xs text-gray-500 font-mono max-w-[160px] truncate">{r.model || '—'}</td>
                  <td className="px-6 py-3.5 text-xs text-gray-600">{fmtSec(r.audio_in_seconds)}</td>
                  <td className="px-6 py-3.5 text-xs text-gray-600">{fmtSec(r.audio_out_seconds)}</td>
                  <td className="px-6 py-3.5 text-xs text-gray-600">{r.input_tokens ?? '—'}</td>
                  <td className="px-6 py-3.5 text-xs text-gray-600">{r.output_tokens ?? '—'}</td>
                  <td className="px-6 py-3.5 text-xs text-gray-600">{fmtSec(r.duration_seconds)}</td>
                  <td className="px-6 py-3.5 text-sm font-semibold text-gray-800">
                    {r.cost_usd != null ? `$${Number(r.cost_usd).toFixed(6)}` : '—'}
                  </td>
                  <td className="px-6 py-3.5 text-xs text-gray-400">
                    {r.created_at ? new Date(r.created_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={page} pages={pages} onPage={setPage} />
      </div>
    </div>
  )
}
