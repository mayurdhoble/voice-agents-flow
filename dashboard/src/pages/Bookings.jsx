import { useEffect, useState, useCallback } from 'react'
import Pagination from '../components/Pagination'

const statusBadge = {
  pending:   'bg-yellow-50 text-yellow-700',
  confirmed: 'bg-green-50 text-green-700',
  cancelled: 'bg-red-50 text-red-700',
  inquiry:   'bg-blue-50 text-blue-700',
}

export default function Bookings() {
  const [bookings, setBookings] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)

  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')

  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput)
      setPage(1)
    }, 400)
    return () => clearTimeout(t)
  }, [searchInput])

  const fetchBookings = useCallback(() => {
    const params = new URLSearchParams({ page, limit: 20 })
    if (search) params.set('search', search)
    if (status) params.set('status', status)

    fetch(`/api/bookings?${params}`)
      .then(r => r.json())
      .then(d => {
        setBookings(d.data || [])
        setTotal(d.total || 0)
        setPages(d.pages || 1)
      })
      .catch(console.error)
  }, [page, search, status])

  useEffect(() => {
    fetchBookings()
  }, [fetchBookings])

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-gray-900">Bookings</h1>
        <p className="text-sm text-gray-500 mt-0.5">{total} bookings total</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <input
          type="text"
          placeholder="Search room type…"
          value={searchInput}
          onChange={e => setSearchInput(e.target.value)}
          className="border border-gray-200 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 w-56"
        />
        <select
          value={status}
          onChange={e => { setStatus(e.target.value); setPage(1) }}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
        >
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="confirmed">Confirmed</option>
          <option value="cancelled">Cancelled</option>
          <option value="inquiry">Inquiry</option>
        </select>
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm">
        <div className="overflow-x-auto">
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
                <tr><td colSpan={10} className="px-6 py-10 text-center text-gray-400">No bookings found</td></tr>
              )}
              {bookings.map(b => (
                <tr key={b.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-3 font-medium text-gray-800">{b.guests?.name || '—'}</td>
                  <td className="px-6 py-3 text-gray-600">{b.guests?.phone || '—'}</td>
                  <td className="px-6 py-3 text-gray-700">{b.room_type || '—'}</td>
                  <td className="px-6 py-3 text-gray-500 whitespace-nowrap">{b.checkin_date || '—'}</td>
                  <td className="px-6 py-3 text-gray-500 whitespace-nowrap">{b.checkout_date || '—'}</td>
                  <td className="px-6 py-3 text-gray-600 text-center">{b.nights ?? '—'}</td>
                  <td className="px-6 py-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium capitalize ${
                      statusBadge[b.status] || 'bg-gray-100 text-gray-600'
                    }`}>{b.status || '—'}</span>
                  </td>
                  <td className="px-6 py-3 text-gray-600">{b.airport_pickup ? 'Yes' : 'No'}</td>
                  <td className="px-6 py-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                      b.whatsapp_sent ? 'bg-green-50 text-green-700' : 'bg-gray-50 text-gray-500'
                    }`}>{b.whatsapp_sent ? 'Sent' : 'No'}</span>
                  </td>
                  <td className="px-6 py-3 text-gray-400 text-xs font-mono">{b.djubo_booking_id || '—'}</td>
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
