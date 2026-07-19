import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, ResponsiveContainer,
} from 'recharts'
import StatsCard from '../components/StatsCard'

const COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6']

export default function Analytics() {
  const [data, setData] = useState(null)
  const [stats, setStats] = useState(null)

  useEffect(() => {
    fetch('/api/analytics').then(r => r.json()).then(setData).catch(console.error)
    fetch('/api/stats').then(r => r.json()).then(setStats).catch(console.error)
  }, [])

  const bookingConversion =
    stats && stats.calls
      ? Math.round((stats.bookings / stats.calls) * 100)
      : 0

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-gray-900">Analytics</h1>
        <p className="text-sm text-gray-500 mt-0.5">Aggregated insights from all call and booking data</p>
      </div>

      {/* Row 1 — 3 stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <StatsCard label="Calls This Week"    value={data?.calls_this_week}  sub="last 7 days" />
        <StatsCard label="Calls This Month"   value={data?.calls_this_month} sub="last 30 days" />
        <StatsCard label="Booking Conversion" value={`${bookingConversion}%`} sub="bookings / total calls" />
      </div>

      {/* Calls over time — full width */}
      <div className="bg-white rounded-xl border border-gray-100 p-6 mb-6">
        <h3 className="text-sm font-semibold text-gray-900 mb-1">Calls Over Time</h3>
        <p className="text-xs text-gray-400 mb-5">Daily call volume — last 30 days</p>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={data?.calls_trend || []} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              tickFormatter={v => v.slice(5)}
              interval={4}
            />
            <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} allowDecimals={false} />
            <Tooltip
              contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
              labelFormatter={v => `Date: ${v}`}
            />
            <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} name="Calls" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Row 2 — Language + Booking Status */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div className="bg-white rounded-xl border border-gray-100 p-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Language Distribution</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={data?.language_dist || []}
                dataKey="count"
                nameKey="language"
                cx="50%"
                cy="50%"
                outerRadius={80}
                label={({ language, percent }) =>
                  `${(language || '').toUpperCase()} ${(percent * 100).toFixed(0)}%`
                }
              >
                {(data?.language_dist || []).map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl border border-gray-100 p-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Booking Status</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={data?.booking_status || []}
                dataKey="count"
                nameKey="status"
                cx="50%"
                cy="50%"
                outerRadius={80}
                label={({ status, percent }) =>
                  `${status} ${(percent * 100).toFixed(0)}%`
                }
              >
                {(data?.booking_status || []).map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Row 3 — Room Types + Direction */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-100 p-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Room Types Booked</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart
              data={data?.room_types || []}
              layout="vertical"
              margin={{ top: 0, right: 20, left: 20, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: '#94a3b8' }} allowDecimals={false} />
              <YAxis
                dataKey="room_type"
                type="category"
                tick={{ fontSize: 10, fill: '#64748b' }}
                width={100}
              />
              <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="count" fill="#22c55e" radius={[0, 4, 4, 0]} name="Bookings" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl border border-gray-100 p-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Call Direction Split</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={data?.direction_dist || []}
                dataKey="count"
                nameKey="direction"
                cx="50%"
                cy="50%"
                outerRadius={80}
                label={({ direction, percent }) =>
                  `${direction} ${(percent * 100).toFixed(0)}%`
                }
              >
                {(data?.direction_dist || []).map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
