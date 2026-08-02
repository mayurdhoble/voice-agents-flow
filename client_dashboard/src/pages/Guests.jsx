import { useEffect, useState } from 'react'
import Pagination from '../components/Pagination'
import { api } from '../lib/api'

export default function Guests() {
  const [data, setData] = useState({ data: [], page: 1, pages: 1, total: 0 })
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')

  const load = () => {
    const p = new URLSearchParams({ page, limit: 20 })
    if (search) p.set('search', search)
    api(`/guests?${p}`).then(setData).catch(() => {})
  }
  useEffect(() => { load() }, [page])
  useEffect(() => { const t = setTimeout(() => { setPage(1); load() }, 400); return () => clearTimeout(t) }, [search])

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto">
      <div className="mb-6 flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Guests</h1>
          <p className="text-sm text-gray-400 mt-0.5">{data.total} guests captured from calls</p>
        </div>
        <input
          value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name…"
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm w-full sm:w-56 focus:outline-none focus:ring-2 focus:ring-stone-800 focus:border-transparent hover:border-gray-300 transition-colors"
        />
      </div>

      <div className="bg-white rounded-xl border border-gray-100">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[360px]">
            <thead>
              <tr className="border-b border-gray-100">
                {['Name', 'Phone', 'First seen'].map(h => (
                  <th key={h} className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.data.length === 0 && (
                <tr><td colSpan={3} className="px-6 py-10 text-center text-gray-400 text-sm">No guests found</td></tr>
              )}
              {data.data.map(g => (
                <tr key={g.id} className="border-b border-gray-50 last:border-0 hover:bg-stone-50/50 transition-colors">
                  <td className="px-4 sm:px-6 py-3.5 font-medium text-gray-800">{g.name || '—'}</td>
                  <td className="px-4 sm:px-6 py-3.5 text-gray-600">{g.phone || '—'}</td>
                  <td className="px-4 sm:px-6 py-3.5 text-gray-400 text-xs">{g.created_at ? new Date(g.created_at).toLocaleDateString() : '—'}</td>
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
