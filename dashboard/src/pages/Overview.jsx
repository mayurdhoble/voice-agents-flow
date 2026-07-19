import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, ResponsiveContainer,
} from 'recharts'
import StatsCard from '../components/StatsCard'

const COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6']

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg px-3 py-2 text-xs">
      <p className="text-gray-500 mb-0.5">{label}</p>
      <p className="font-semibold text-gray-900">{payload[0].value} calls</p>
    </div>
  )
}

export default function Overview() {
  const [stats, setStats] = useState(null)
  const [analytics, setAnalytics] = useState(null)
  const [calls, setCalls] = useState([])

  useEffect(() => {
    fetch('/api/stats').then(r => r.json()).then(setStats).catch(console.error)
    fetch('/api/analytics').then(r => r.json()).then(setAnalytics).catch(console.error)
    fetch('/api/calls?limit=5').then(r => r.json()).then(d => setCalls(d.data || [])).catch(console.error)
  }, [])

  const bookingConversion = stats?.calls
    ? Math.round((stats.bookings / stats.calls) * 100)
    : 0

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-gray-900">Overview</h1>
        <p className="text-sm text-gray-500 mt-0.5">Live summary across all calls and bookings</p>
      </div>

      {/* Row 1 — primary metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-4">
        <StatsCard label="Total Calls"   value={stats?.calls}         />
        <StatsCard label="Guests"        value={stats?.guests}        />
        <StatsCard label="Bookings"      value={stats?.bookings}      />
        <StatsCard label="Events"        value={stats?.events}        />
        <StatsCard label="WhatsApp Sent" value={stats?.whatsapp_sent} />
      </div>

      {/* Row 2 — secondary metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        <StatsCard label="Calls This Week"    value={analytics?.calls_this_week}  sub="last 7 days" />
        <StatsCard label="Calls This Month"   value={analytics?.calls_this_month} sub="last 30 days" />
        <StatsCard label="Booking Conversion" value={`${bookingConversion}%`}     sub="bookings / total calls" />
      </div>

      {/* Calls trend */}
      <div className="bg-white rounded-xl border border-gray-100 p-6 mb-6">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Call Volume</h2>
            <p className="text-xs text-gray-400 mt-0.5">Last 30 days</p>
          </div>
          <span className="text-xs text-gray-400 bg-gray-50 px-2.5 py-1 rounded-full border border-gray-100">
            {analytics?.calls_this_month ?? 0} this month
          </span>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={analytics?.calls_trend || []} margin={{ top: 0, right: 0, left: -28, bottom: 0 }}>
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
              allowDecimals={false}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: '#f8fafc' }} />
            <Bar dataKey="count" fill="#6366f1" radius={[3, 3, 0, 0]} maxBarSize={32} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <div className="bg-white rounded-xl border border-gray-100 p-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-1">Language Distribution</h2>
          <p className="text-xs text-gray-400 mb-5">By call language</p>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie
                data={analytics?.language_dist || []}
                dataKey="count"
                nameKey="language"
                cx="50%"
                cy="50%"
                innerRadius={48}
                outerRadius={72}
                paddingAngle={3}
              >
                {(analytics?.language_dist || []).map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} strokeWidth={0} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12, boxShadow: '0 4px 6px -1px rgba(0,0,0,.08)' }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-3 mt-3">
            {(analytics?.language_dist || []).map((d, i) => (
              <span key={i} className="flex items-center gap-1.5 text-xs text-gray-600">
                <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
                {(d.language || 'unknown').toUpperCase()} — {d.count}
              </span>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-100 p-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-1">Call Direction</h2>
          <p className="text-xs text-gray-400 mb-5">Inbound vs outbound</p>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie
                data={analytics?.direction_dist || []}
                dataKey="count"
                nameKey="direction"
                cx="50%"
                cy="50%"
                innerRadius={48}
                outerRadius={72}
                paddingAngle={3}
              >
                {(analytics?.direction_dist || []).map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} strokeWidth={0} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12, boxShadow: '0 4px 6px -1px rgba(0,0,0,.08)' }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-3 mt-3">
            {(analytics?.direction_dist || []).map((d, i) => (
              <span key={i} className="flex items-center gap-1.5 text-xs text-gray-600">
                <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
                {d.direction} — {d.count}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Recent calls */}
      <div className="bg-white rounded-xl border border-gray-100">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-900">Recent Calls</h2>
          <a href="/calls" className="text-xs text-indigo-600 hover:text-indigo-700 font-medium">View all</a>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Phone</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Direction</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Language</th>
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
                  <td className="px-6 py-3.5">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                      c.direction === 'outbound'
                        ? 'bg-blue-50 text-blue-700'
                        : 'bg-emerald-50 text-emerald-700'
                    }`}>{c.direction}</span>
                  </td>
                  <td className="px-6 py-3.5 text-xs font-medium text-gray-500 uppercase tracking-wide">{c.language || '—'}</td>
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
