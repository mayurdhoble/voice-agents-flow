import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import Pagination from '../components/Pagination'

const TEMPLATE_LABELS = {
  booking_confirmation: 'Booking Confirmation',
  event_confirmation:   'Event Confirmation',
}

export default function WhatsApp() {
  const [data, setData] = useState({ data: [], page: 1, pages: 1, total: 0 })
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState('all')

  const load = () => {
    const p = new URLSearchParams({ page, limit: 20 })
    if (statusFilter !== 'all') p.set('status', statusFilter)
    api(`/whatsapp?${p}`).then(setData).catch(() => {})
  }

  useEffect(() => { load() }, [page, statusFilter])

  const guestName = (row) => row.bookings?.guests?.name || '—'
  const guestPhone = (row) => row.phone || row.bookings?.guests?.phone || '—'

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-6 flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">WhatsApp</h1>
          <p className="text-sm text-gray-500 mt-0.5">{data.total} messages sent to guests</p>
        </div>
        <div className="flex gap-2">
          {['all', 'sent', 'failed'].map(s => (
            <button key={s}
              onClick={() => { setStatusFilter(s); setPage(1) }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                statusFilter === s
                  ? 'bg-gray-800 text-white border-gray-800'
                  : 'bg-white text-gray-500 border-gray-200 hover:border-gray-400'
              }`}>
              {s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-100">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                {['Guest', 'Phone', 'Message Type', 'Status', 'Sent At'].map(h => (
                  <th key={h} className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.data.length === 0 && (
                <tr><td colSpan={5} className="px-6 py-10 text-center text-gray-400 text-sm">No messages found</td></tr>
              )}
              {data.data.map(row => (
                <tr key={row.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50 transition-colors">
                  <td className="px-6 py-3.5 font-medium text-gray-800">{guestName(row)}</td>
                  <td className="px-6 py-3.5 text-gray-500 text-xs font-mono">{guestPhone(row)}</td>
                  <td className="px-6 py-3.5">
                    <span className="text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full font-medium">
                      {TEMPLATE_LABELS[row.template_name] || row.template_name || '—'}
                    </span>
                  </td>
                  <td className="px-6 py-3.5">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                      row.status === 'sent'
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-red-100 text-red-600'
                    }`}>
                      {row.status === 'sent' ? '✓ Sent' : '✗ Failed'}
                    </span>
                  </td>
                  <td className="px-6 py-3.5 text-gray-400 text-xs">
                    {row.sent_at ? new Date(row.sent_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={data.page} pages={data.pages} onPage={setPage} />
      </div>
    </div>
  )
}
