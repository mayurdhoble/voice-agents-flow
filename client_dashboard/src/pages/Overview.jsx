import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, ResponsiveContainer,
} from 'recharts'
import StatsCard from '../components/StatsCard'
import { api } from '../lib/api'

const COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6']

export default function Overview() {
  const [o, setO] = useState(null)
  const [ins, setIns] = useState(null)
  const [calls, setCalls] = useState([])

  useEffect(() => {
    api('/overview').then(setO).catch(() => {})
    api('/insights').then(setIns).catch(() => {})
    api('/calls?limit=6').then(d => setCalls(d.data || [])).catch(() => {})
  }, [])

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-gray-900">Overview</h1>
        <p className="text-sm text-gray-500 mt-0.5">How your AI receptionist is performing</p>
      </div>

      {/* Needs-attention banner */}
      {o?.needs_attention > 0 && (
        <Link to="/attention"
          className="flex items-center justify-between bg-amber-50 border border-amber-200 rounded-xl px-5 py-4 mb-6 hover:bg-amber-100/60 transition-colors">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-amber-500 flex items-center justify-center text-white text-lg font-bold">!</div>
            <div>
              <p className="text-sm font-semibold text-amber-900">{o.needs_attention} booking{o.needs_attention > 1 ? 's' : ''} need your attention</p>
              <p className="text-xs text-amber-700">Unconfirmed bookings that may need a manual follow-up.</p>
            </div>
          </div>
          <span className="text-xs font-medium text-amber-800">Review →</span>
        </Link>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
        <StatsCard label="Calls Handled"   value={o?.total_calls} sub={`${o?.calls_this_week ?? 0} this week`} />
        <StatsCard label="Bookings"        value={o?.total_bookings} sub={`${o?.conversion_rate ?? 0}% of calls`} />
        <StatsCard label="Confirmed"       value={o?.confirmed_bookings} accent="text-emerald-600" />
        <StatsCard label="Needs Attention" value={o?.needs_attention} accent="text-amber-600" />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatsCard label="Guests"        value={o?.total_guests} />
        <StatsCard label="Event Enquiries" value={o?.total_events} />
        <StatsCard label="Nights Booked" value={o?.total_nights_booked} />
        <StatsCard label="Calls / Month" value={o?.calls_this_month} sub="last 30 days" />
      </div>

      {/* Call volume */}
      <div className="bg-white rounded-xl border border-gray-100 p-6 mb-6">
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
            <Bar dataKey="count" fill="#6366f1" radius={[3, 3, 0, 0]} maxBarSize={32} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <div className="bg-white rounded-xl border border-gray-100 p-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-1">Guest Languages</h2>
          <p className="text-xs text-gray-400 mb-5">What your callers speak</p>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={ins?.language_dist || []} dataKey="count" nameKey="language" cx="50%" cy="50%" innerRadius={48} outerRadius={72} paddingAngle={3}>
                {(ins?.language_dist || []).map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} strokeWidth={0} />)}
              </Pie>
              <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-3 mt-3">
            {(ins?.language_dist || []).map((d, i) => (
              <span key={i} className="flex items-center gap-1.5 text-xs text-gray-600">
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                {(d.language || 'unknown').toUpperCase()} — {d.count}
              </span>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-100 p-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-1">Busiest Hours</h2>
          <p className="text-xs text-gray-400 mb-5">When guests call (IST)</p>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={ins?.peak_hours || []} margin={{ top: 0, right: 0, left: -28, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="hour" tick={{ fontSize: 9, fill: '#94a3b8' }} interval={3} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} allowDecimals={false} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }} cursor={{ fill: '#f8fafc' }} />
              <Bar dataKey="count" fill="#22c55e" radius={[3, 3, 0, 0]} maxBarSize={14} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Recent calls */}
      <div className="bg-white rounded-xl border border-gray-100">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-900">Recent Calls</h2>
          <Link to="/calls" className="text-xs text-indigo-600 hover:text-indigo-700 font-medium">View all</Link>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Phone</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Language</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Recording</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Time</th>
              </tr>
            </thead>
            <tbody>
              {calls.length === 0 && (
                <tr><td colSpan={4} className="px-6 py-10 text-center text-gray-400 text-sm">No calls yet</td></tr>
              )}
              {calls.map(c => (
                <tr key={c.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50 transition-colors">
                  <td className="px-6 py-3.5 font-medium text-gray-800">{c.phone_number || '—'}</td>
                  <td className="px-6 py-3.5 text-xs font-medium text-gray-500 uppercase tracking-wide">{c.language || '—'}</td>
                  <td className="px-6 py-3.5">{c.recording_url
                    ? <span className="text-emerald-600 text-xs">● Available</span>
                    : <span className="text-gray-300 text-xs">—</span>}</td>
                  <td className="px-6 py-3.5 text-gray-400 text-xs">{c.created_at ? new Date(c.created_at).toLocaleString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
