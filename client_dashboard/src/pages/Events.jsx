import { useEffect, useState } from 'react'
import Pagination from '../components/Pagination'
import { api } from '../lib/api'

export default function Events() {
  const [data, setData] = useState({ data: [], page: 1, pages: 1, total: 0 })
  const [page, setPage] = useState(1)

  useEffect(() => {
    api(`/events?page=${page}&limit=20`).then(setData).catch(() => {})
  }, [page])

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Event Enquiries</h1>
        <p className="text-sm text-gray-400 mt-0.5">{data.total} party / function enquiries for your events team to follow up</p>
      </div>

      <div className="bg-white rounded-xl border border-gray-100">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[520px]">
            <thead>
              <tr className="border-b border-gray-100">
                {['Guest', 'Event', 'Date', 'Guests', 'Status', 'Received'].map(h => (
                  <th key={h} className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.data.length === 0 && (
                <tr><td colSpan={6} className="px-6 py-10 text-center text-gray-400 text-sm">No event enquiries yet</td></tr>
              )}
              {data.data.map(e => (
                <tr key={e.id} className="border-b border-gray-50 last:border-0 hover:bg-stone-50/50 transition-colors">
                  <td className="px-4 sm:px-6 py-3.5">
                    <p className="font-medium text-gray-800">{e.guests?.name || '—'}</p>
                    <p className="text-xs text-gray-400">{e.guests?.phone || ''}</p>
                  </td>
                  <td className="px-4 sm:px-6 py-3.5 text-gray-700 capitalize">{e.event_type || '—'}</td>
                  <td className="px-4 sm:px-6 py-3.5 text-gray-500 text-xs">{e.event_date || '—'}</td>
                  <td className="px-4 sm:px-6 py-3.5 text-gray-500 tabular-nums">{e.num_guests ?? '—'}</td>
                  <td className="px-4 sm:px-6 py-3.5">
                    <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-stone-100 text-stone-700 capitalize">
                      {e.status || 'inquiry'}
                    </span>
                  </td>
                  <td className="px-4 sm:px-6 py-3.5 text-gray-400 text-xs">{e.created_at ? new Date(e.created_at).toLocaleDateString() : '—'}</td>
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
