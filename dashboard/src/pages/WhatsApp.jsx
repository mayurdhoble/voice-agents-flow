import { useEffect, useState, useCallback } from 'react'
import Pagination from '../components/Pagination'

const statusBadge = {
  sent:      'bg-blue-50 text-blue-700',
  delivered: 'bg-green-50 text-green-700',
  failed:    'bg-red-50 text-red-700',
}

export default function WhatsApp() {
  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [status, setStatus] = useState('')

  const fetchLogs = useCallback(() => {
    const params = new URLSearchParams({ page, limit: 20 })
    if (status) params.set('status', status)

    fetch(`/api/whatsapp?${params}`)
      .then(r => r.json())
      .then(d => {
        setLogs(d.data || [])
        setTotal(d.total || 0)
        setPages(d.pages || 1)
      })
      .catch(console.error)
  }, [page, status])

  useEffect(() => {
    fetchLogs()
  }, [fetchLogs])

  return (
    <div className="p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">WhatsApp Logs</h2>
      <p className="text-sm text-gray-500 mb-6">{total} messages logged</p>

      {/* Filter */}
      <div className="flex gap-3 mb-5">
        <select
          value={status}
          onChange={e => { setStatus(e.target.value); setPage(1) }}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
        >
          <option value="">All statuses</option>
          <option value="sent">Sent</option>
          <option value="delivered">Delivered</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left">
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Phone</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Template</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Sent At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {logs.length === 0 && (
                <tr><td colSpan={4} className="px-6 py-10 text-center text-gray-400">No WhatsApp logs found</td></tr>
              )}
              {logs.map(l => (
                <tr key={l.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-3 font-medium text-gray-800">{l.phone || '—'}</td>
                  <td className="px-6 py-3 text-gray-600">{l.template_name || '—'}</td>
                  <td className="px-6 py-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium capitalize ${
                      statusBadge[l.status] || 'bg-gray-100 text-gray-600'
                    }`}>{l.status || '—'}</span>
                  </td>
                  <td className="px-6 py-3 text-gray-500 whitespace-nowrap">
                    {l.sent_at ? new Date(l.sent_at).toLocaleString() : '—'}
                  </td>
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
