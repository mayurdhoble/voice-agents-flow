import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, ResponsiveContainer,
} from 'recharts'
import StatsCard from '../components/StatsCard'
import { api } from '../lib/api'
import { fmtDateTime, fmtDur, fmtPhone, LeadBadge, INTENT_LABELS } from '../lib/format'

const COLORS = ['#2B7FFF', '#0A1628', '#60A5FA', '#1E40AF', '#93C5FD', '#1D4ED8']

function Donut({ title, sub, data, nameKey, label }) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 p-4 sm:p-6 card-hover">
      <h2 className="text-sm font-semibold text-gray-900 mb-1">{title}</h2>
      <p className="text-xs text-gray-400 mb-5">{sub}</p>
      <ResponsiveContainer width="100%" height={180}>
        <PieChart>
          <Pie data={data} dataKey="count" nameKey={nameKey} cx="50%" cy="50%" innerRadius={48} outerRadius={72} paddingAngle={3}>
            {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} strokeWidth={0} />)}
          </Pie>
          <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }} />
        </PieChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap gap-3 mt-3">
        {data.map((d, i) => (
          <span key={i} className="flex items-center gap-1.5 text-xs text-gray-600">
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
            {label(d[nameKey])} — {d.count}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function Overview() {
  const [o, setO] = useState(null)
  const [ins, setIns] = useState(null)
  const [calls, setCalls] = useState([])

  useEffect(() => {
    api('/overview').then(setO).catch(() => {})
    api('/insights').then(setIns).catch(() => {})
    api('/calls?limit=6').then(d => setCalls(d.data || [])).catch(() => {})
  }, [])

  const avg = o?.avg_call_seconds != null ? fmtDur({ duration_seconds: o.avg_call_seconds }) : '—'

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto">
      <div className="mb-6 sm:mb-8">
        <h1 className="text-xl font-semibold text-gray-900">Overview</h1>
        <p className="text-sm text-gray-400 mt-0.5">How Nora, your AI receptionist, is doing</p>
      </div>

      {/* Callbacks banner */}
      {o?.callbacks_pending > 0 && (
        <Link to="/callbacks"
          className="flex items-center justify-between bg-amber-50 border border-amber-200 rounded-xl px-4 sm:px-5 py-4 mb-6 hover:bg-amber-100/60 transition-colors group">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-amber-500 flex items-center justify-center text-white text-lg font-bold shrink-0">!</div>
            <div>
              <p className="text-sm font-semibold text-amber-900">{o.callbacks_pending} guest{o.callbacks_pending > 1 ? 's' : ''} waiting for a callback</p>
              <p className="text-xs text-amber-700">Guests who asked about booking, rates or events — Nora told them our team will reach out.</p>
            </div>
          </div>
          <span className="hidden sm:inline text-xs font-medium text-amber-800 shrink-0 group-hover:translate-x-0.5 transition-transform">Review →</span>
        </Link>
      )}

      {/* KPI rows */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-3 sm:mb-4">
        <StatsCard label="Calls Handled"     value={o?.total_calls}        sub={`${o?.calls_this_week ?? 0} this week`} />
        <StatsCard label="Calls Today"       value={o?.calls_today} />
        <StatsCard label="Callbacks Waiting" value={o?.callbacks_pending}   accent="text-amber-600" />
        <StatsCard label="Guests Contacted"  value={o?.callbacks_contacted} accent="text-emerald-600" />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6 sm:mb-8">
        <StatsCard label="Hot Leads"          value={o?.hot_leads}  accent="text-red-600" sub={`${o?.warm_leads ?? 0} warm`} />
        <StatsCard label="WhatsApp Chats"     value={o?.whatsapp_conversations} />
        <StatsCard label="Avg Call Length"    value={avg} />
        <StatsCard label="Total AI Minutes"   value={o?.total_minutes != null ? `${o.total_minutes}m` : '—'} sub="all calls ever" />
      </div>

      {/* Call volume chart */}
      <div className="bg-white rounded-xl border border-gray-100 p-4 sm:p-6 mb-6 card-hover">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Call Volume</h2>
            <p className="text-xs text-gray-400 mt-0.5">Last 30 days</p>
          </div>
          <span className="text-xs text-gray-400 bg-gray-50 px-2.5 py-1 rounded-full border border-gray-100">
            {o?.calls_this_month ?? 0} this month
          </span>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={ins?.calls_trend || []} margin={{ top: 0, right: 0, left: -28, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={v => v.slice(5)} interval={4} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} allowDecimals={false} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }} cursor={{ fill: '#f8fafc' }} />
            <Bar dataKey="count" fill="#2B7FFF" radius={[3, 3, 0, 0]} maxBarSize={32} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 sm:gap-6 mb-6 sm:mb-8">
        <Donut title="What Guests Call About" sub="Reason for each call"
               data={ins?.intent_dist || []} nameKey="intent" label={k => INTENT_LABELS[k] || k} />
        <Donut title="Guest Languages" sub="What your callers speak"
               data={ins?.language_dist || []} nameKey="language" label={k => (k || 'unknown').toUpperCase()} />

        <div className="bg-white rounded-xl border border-gray-100 p-4 sm:p-6 card-hover md:col-span-2 xl:col-span-1">
          <h2 className="text-sm font-semibold text-gray-900 mb-1">Busiest Hours</h2>
          <p className="text-xs text-gray-400 mb-5">When guests call (IST)</p>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={ins?.peak_hours || []} margin={{ top: 0, right: 0, left: -28, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="hour" tick={{ fontSize: 9, fill: '#94a3b8' }} interval={3} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} allowDecimals={false} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }} cursor={{ fill: '#f8fafc' }} />
              <Bar dataKey="count" fill="#0A1628" radius={[3, 3, 0, 0]} maxBarSize={14} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Recent calls */}
      <div className="bg-white rounded-xl border border-gray-100">
        <div className="px-4 sm:px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-900">Recent Calls</h2>
          <Link to="/calls" className="text-xs text-stone-600 hover:text-stone-900 font-medium transition-colors">View all →</Link>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[560px]">
            <thead>
              <tr className="border-b border-gray-100">
                {['Phone', 'Lead', 'Duration', 'Recording', 'Time'].map(h => (
                  <th key={h} className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {calls.length === 0 && (
                <tr><td colSpan={5} className="px-6 py-10 text-center text-gray-400 text-sm">No calls yet</td></tr>
              )}
              {calls.map(c => (
                <tr key={c.id} className="border-b border-gray-50 last:border-0 hover:bg-stone-50/50 transition-colors">
                  <td className="px-4 sm:px-6 py-3.5 font-medium text-gray-800">{c.guest_name || fmtPhone(c.phone_number) || 'Unknown caller'}</td>
                  <td className="px-4 sm:px-6 py-3.5"><LeadBadge lead={c.lead_temperature} /></td>
                  <td className="px-4 sm:px-6 py-3.5 text-gray-500 text-xs">{fmtDur(c)}</td>
                  <td className="px-4 sm:px-6 py-3.5">{c.recording_url
                    ? <span className="text-emerald-600 text-xs font-medium">● Available</span>
                    : <span className="text-gray-300 text-xs">—</span>}</td>
                  <td className="px-4 sm:px-6 py-3.5 text-gray-400 text-xs">{fmtDateTime(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
