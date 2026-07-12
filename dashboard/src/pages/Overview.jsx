import { useEffect, useState } from 'react'
import StatsCard from '../components/StatsCard'

export default function Overview() {
  const [stats, setStats] = useState(null)
  const [calls, setCalls] = useState([])

  useEffect(() => {
    fetch('/api/stats').then(r => r.json()).then(setStats).catch(console.error)
    fetch('/api/calls?limit=5').then(r => r.json()).then(setCalls).catch(console.error)
  }, [])

  return (
    <div className="p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">Overview</h2>
      <p className="text-sm text-gray-500 mb-6">Live summary from all calls</p>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
        <StatsCard label="Total Calls"    value={stats?.calls}         icon="📞" color="indigo" />
        <StatsCard label="Guests"         value={stats?.guests}        icon="👤" color="blue"   />
        <StatsCard label="Bookings"       value={stats?.bookings}      icon="🛏️" color="green"  />
        <StatsCard label="Events"         value={stats?.events}        icon="🎉" color="yellow" />
        <StatsCard label="WhatsApp Sent"  value={stats?.whatsapp_sent} icon="💬" color="purple" />
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-800">Recent Calls</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left">
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Phone</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Direction</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Language</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {calls.length === 0 && (
                <tr><td colSpan={4} className="px-6 py-8 text-center text-gray-400">No calls yet</td></tr>
              )}
              {calls.map(c => (
                <tr key={c.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-3 font-medium text-gray-800">{c.phone_number || '—'}</td>
                  <td className="px-6 py-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                      c.direction === 'outbound' ? 'bg-blue-50 text-blue-700' : 'bg-green-50 text-green-700'
                    }`}>{c.direction}</span>
                  </td>
                  <td className="px-6 py-3 uppercase text-gray-600">{c.language}</td>
                  <td className="px-6 py-3 text-gray-500">{c.created_at ? new Date(c.created_at).toLocaleString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
