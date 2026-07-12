import { useEffect, useState } from 'react'

const statusColors = {
  pending:   'bg-yellow-50 text-yellow-700',
  confirmed: 'bg-green-50  text-green-700',
  cancelled: 'bg-red-50    text-red-700',
}

export default function Bookings() {
  const [bookings, setBookings] = useState([])

  useEffect(() => {
    fetch('/api/bookings?limit=100').then(r => r.json()).then(setBookings).catch(console.error)
  }, [])

  return (
    <div className="p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">Bookings</h2>
      <p className="text-sm text-gray-500 mb-6">{bookings.length} booking(s) recorded</p>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left">
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Guest</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Phone</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Room</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Check-in</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Check-out</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Nights</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Pickup</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">WhatsApp</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Djubo ID</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {bookings.length === 0 && (
              <tr><td colSpan={10} className="px-6 py-10 text-center text-gray-400">No bookings yet</td></tr>
            )}
            {bookings.map(b => (
              <tr key={b.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-6 py-3 font-medium text-gray-800">{b.guests?.name || '—'}</td>
                <td className="px-6 py-3 text-gray-600">{b.guests?.phone || '—'}</td>
                <td className="px-6 py-3 text-gray-700">{b.room_type || '—'}</td>
                <td className="px-6 py-3 text-gray-600 whitespace-nowrap">{b.checkin_date || '—'}</td>
                <td className="px-6 py-3 text-gray-600 whitespace-nowrap">{b.checkout_date || '—'}</td>
                <td className="px-6 py-3 text-gray-600 text-center">{b.nights ?? '—'}</td>
                <td className="px-6 py-3">
                  <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${statusColors[b.status] || ''}`}>
                    {b.status}
                  </span>
                </td>
                <td className="px-6 py-3 text-center">
                  {b.airport_pickup ? '✅' : '—'}
                </td>
                <td className="px-6 py-3 text-center">
                  {b.whatsapp_sent ? '✅' : '⏳'}
                </td>
                <td className="px-6 py-3 text-xs text-gray-500 font-mono">{b.djubo_booking_id || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
