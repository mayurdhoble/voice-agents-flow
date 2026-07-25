import { useEffect, useState } from 'react'
import Pagination from '../components/Pagination'
import { api } from '../lib/api'

const STATUS_STYLES = {
  confirmed: 'bg-emerald-50 text-emerald-700',
  pending:   'bg-amber-50 text-amber-700',
  cancelled: 'bg-red-50 text-red-700',
}

export default function Bookings() {
  const [data, setData] = useState({ data: [], page: 1, pages: 1, total: 0 })
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')

  const load = () => {
    const p = new URLSearchParams({ page, limit: 20 })
    if (status) p.set('status', status)
    api(`/bookings?${p}`).then(setData).catch(() => {})
  }
  useEffect(() => { load() }, [page, status])

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-6 flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Bookings</h1>
          <p className="text-sm text-gray-500 mt-0.5">{data.total} bookings captured by your AI receptionist</p>
        </div>
        <div className="flex gap-1.5">
          {['', 'confirmed', 'pending', 'cancelled'].map(s => (
            <button key={s} onClick={() => { setStatus(s); setPage(1) }}
              className={`px-3 py-1.5 text-xs rounded-lg border capitalize transition-colors ${
                status === s ? 'bg-indigo-600 text-white border-indigo-600' : 'border-gray-200 text-gray-600 hover:bg-gray-50'}`}>
              {s || 'All'}
            </button>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-100">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                {['Guest', 'Room', 'Check-in', 'Check-out', 'Nights', 'Status', 'PMS', 'Created'].map(h => (
                  <th key={h} className="px-5 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.data.length === 0 && (
                <tr><td colSpan={8} className="px-6 py-10 text-center text-gray-400 text-sm">No bookings found</td></tr>
              )}
              {data.data.map(b => (
                <tr key={b.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50 transition-colors">
                  <td className="px-5 py-3.5">
                    <p className="font-medium text-gray-800">{b.guests?.name || '—'}</p>
                    <p className="text-xs text-gray-400">{b.guests?.phone || ''}</p>
                  </td>
                  <td className="px-5 py-3.5 text-gray-700">{b.room_type || '—'}</td>
                  <td className="px-5 py-3.5 text-gray-500 text-xs">{b.checkin_date || '—'}</td>
                  <td className="px-5 py-3.5 text-gray-500 text-xs">{b.checkout_date || '—'}</td>
                  <td className="px-5 py-3.5 text-gray-500 tabular-nums">{b.nights ?? '—'}</td>
                  <td className="px-5 py-3.5">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium capitalize ${STATUS_STYLES[b.status] || 'bg-gray-100 text-gray-600'}`}>
                      {b.status || 'pending'}
                    </span>
                  </td>
                  <td className="px-5 py-3.5">{b.djubo_booking_id
                    ? <span className="text-emerald-600 text-xs">Synced</span>
                    : <span className="text-gray-300 text-xs">—</span>}</td>
                  <td className="px-5 py-3.5 text-gray-400 text-xs">{b.created_at ? new Date(b.created_at).toLocaleDateString() : '—'}</td>
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
