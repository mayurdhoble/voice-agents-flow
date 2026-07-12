import { useEffect, useState } from 'react'

const statusColors = {
  inquiry:   'bg-blue-50   text-blue-700',
  confirmed: 'bg-green-50  text-green-700',
  cancelled: 'bg-red-50    text-red-700',
}

export default function Events() {
  const [events, setEvents] = useState([])

  useEffect(() => {
    fetch('/api/events?limit=100').then(r => r.json()).then(setEvents).catch(console.error)
  }, [])

  return (
    <div className="p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">Events</h2>
      <p className="text-sm text-gray-500 mb-6">{events.length} event inquiry(s)</p>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left">
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Guest</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Phone</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Event Type</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Date</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Guests</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Received</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {events.length === 0 && (
              <tr><td colSpan={7} className="px-6 py-10 text-center text-gray-400">No event inquiries yet</td></tr>
            )}
            {events.map(e => (
              <tr key={e.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-6 py-3 font-medium text-gray-800">{e.guests?.name || '—'}</td>
                <td className="px-6 py-3 text-gray-600">{e.guests?.phone || '—'}</td>
                <td className="px-6 py-3 capitalize text-gray-700">{e.event_type || '—'}</td>
                <td className="px-6 py-3 text-gray-600 whitespace-nowrap">{e.event_date || '—'}</td>
                <td className="px-6 py-3 text-gray-600 text-center">{e.num_guests ?? '—'}</td>
                <td className="px-6 py-3">
                  <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${statusColors[e.status] || ''}`}>
                    {e.status}
                  </span>
                </td>
                <td className="px-6 py-3 text-gray-500 whitespace-nowrap">
                  {e.created_at ? new Date(e.created_at).toLocaleDateString() : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
