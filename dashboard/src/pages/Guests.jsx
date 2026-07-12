import { useEffect, useState } from 'react'

export default function Guests() {
  const [guests, setGuests] = useState([])

  useEffect(() => {
    fetch('/api/guests?limit=100').then(r => r.json()).then(setGuests).catch(console.error)
  }, [])

  return (
    <div className="p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">Guests</h2>
      <p className="text-sm text-gray-500 mb-6">{guests.length} guest profile(s)</p>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left">
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Name</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Phone</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Email</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Djubo Tracker</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">First Seen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {guests.length === 0 && (
              <tr><td colSpan={5} className="px-6 py-10 text-center text-gray-400">No guests yet</td></tr>
            )}
            {guests.map(g => (
              <tr key={g.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-6 py-3 font-medium text-gray-800">{g.name || '—'}</td>
                <td className="px-6 py-3 text-gray-600">{g.phone}</td>
                <td className="px-6 py-3 text-gray-600">{g.email || '—'}</td>
                <td className="px-6 py-3 text-xs text-gray-500 font-mono">{g.djubo_tracker_id || '—'}</td>
                <td className="px-6 py-3 text-gray-500 whitespace-nowrap">
                  {g.created_at ? new Date(g.created_at).toLocaleDateString() : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
